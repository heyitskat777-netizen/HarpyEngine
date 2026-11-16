"""Owner-private, revision-bound synthetic assistance in the existing campaign store.

Approval records a human review only. There is deliberately no apply, posting,
consent, dice, or canonical-state operation in this service.
"""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.activity import (
    AssistanceRecord,
    AssistanceView,
    ContextView,
    GenerateDraft,
    MutationResult,
    RequestAssistance,
    ReviewDraft,
)
from girlframe.ai.context import build_context
from girlframe.ai.contracts import (
    AssistanceContext,
    Audience,
    GenerationRequest,
    GenerationResponse,
    Provider,
    validate_response,
)
from girlframe.ai.synthetic import SyntheticProvider
from girlframe.database import tables as t
from girlframe.services.character_transfer import CharacterTransferService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class AssistanceService:
    def __init__(self, store: OnboardingStore, provider: Provider | None = None):
        self.store = store
        self.transfer = CharacterTransferService(store)
        # Injection is for deterministic local fakes; no network provider is shipped.
        self.provider = provider if provider is not None else SyntheticProvider()

    def _authorize(self, c: Connection, viewer: GuildViewer, audience: Audience) -> None:
        self.transfer._authorize(c, viewer)
        if audience == "gm":
            self.store.administrator(viewer)
        elif audience == "handler":
            HandlerService(self.store).authorize(c, viewer)
        elif audience != "player":
            raise WorkflowError("UNSUPPORTED_AUDIENCE: select player, gm or handler.")

    def _revision(self, c: Connection) -> int:
        return int(
            c.execute(
                sa.select(t.campaigns.c.revision).where(t.campaigns.c.id == self.store.campaign_id)
            ).scalar_one()
        )

    def _expect(self, c: Connection, revision: int) -> None:
        if self._revision(c) != revision:
            raise WorkflowError("STALE_CAMPAIGN: refresh before making a new request.")

    def _unpaused(self, c: Connection) -> None:
        if c.execute(
            sa.select(t.pauses.c.user_id).where(t.pauses.c.campaign_id == self.store.campaign_id)
        ).first():
            raise WorkflowError("SAFETY_PAUSED: new assistance and approval are paused.")

    def _context(
        self, c: Connection, viewer: GuildViewer, audience: Audience, revision: int
    ) -> AssistanceContext:
        self._authorize(c, viewer, audience)
        query = (
            sa.select(t.characters.c.user_id)
            .join(
                t.members,
                sa.and_(
                    t.members.c.campaign_id == t.characters.c.campaign_id,
                    t.members.c.user_id == t.characters.c.user_id,
                ),
            )
            .where(
                t.characters.c.campaign_id == self.store.campaign_id,
                t.members.c.active.is_(True),
            )
            .order_by(t.characters.c.user_id)
            .limit(25)
        )
        if audience == "player":
            query = query.where(t.characters.c.user_id == str(viewer.user_id))
        owners = tuple(c.scalars(query))
        if len(owners) > 24:
            raise WorkflowError("CONTEXT_LIMIT: this reference summary supports 24 characters.")
        # The surrounding BEGIN IMMEDIATE prevents source writes while these
        # existing authorized projection readers open their own connections.
        projections = tuple(
            self.transfer.snapshot(viewer, audience="public", owner=int(owner)) for owner in owners
        )
        return build_context(
            campaign_id=self.store.campaign_id,
            requester_id=str(viewer.user_id),
            audience=audience,
            campaign_revision=revision,
            projections=projections,
        )

    def context(self, viewer: GuildViewer, audience: Audience = "player") -> ContextView:
        with self.store.transaction() as c:
            self._authorize(c, viewer, audience)
            context = self._context(c, viewer, audience, self._revision(c))
            return ContextView(context=context, context_digest=context.digest)

    def _owned(self, c: Connection, viewer: GuildViewer, proposal_id: str) -> AssistanceRecord:
        self.transfer._authorize(c, viewer)
        row = c.execute(
            sa.select(t.ai_proposals.c.body_json)
            .where(
                t.ai_proposals.c.campaign_id == self.store.campaign_id,
                t.ai_proposals.c.owner_id == str(viewer.user_id),
                t.ai_proposals.c.proposal_id == proposal_id,
            )
            .order_by(t.ai_proposals.c.revision.desc())
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise WorkflowError("ASSISTANCE_UNAVAILABLE: no private record is available to you.")
        record = AssistanceRecord.model_validate_json(row)
        self._authorize(c, viewer, record.context.audience)
        return record

    def _sources_current(
        self, c: Connection, viewer: GuildViewer, record: AssistanceRecord
    ) -> bool:
        # Normalize the chronology marker to the saved snapshot. Own assistance
        # events advance campaign revision without changing the cited sources.
        try:
            current = self._context(
                c, viewer, record.context.audience, record.context.campaign_revision
            )
        except (ValueError, WorkflowError):
            return False
        return current.digest == record.context.digest

    def _ready(
        self, c: Connection, viewer: GuildViewer, record: AssistanceRecord, command: GenerateDraft
    ) -> None:
        self._expect(c, command.expected_campaign_revision)
        if record.revision != command.expected_proposal_revision:
            raise WorkflowError("STALE_PROPOSAL: reopen the private review.")
        if not self._sources_current(c, viewer, record):
            raise WorkflowError(
                "STALE_CONTEXT: request a fresh summary; saved history is preserved."
            )

    def _append(
        self, c: Connection, viewer: GuildViewer, key: str, record: AssistanceRecord
    ) -> dict[str, Any]:
        # Generic events/command receipts contain metadata, never prompts or drafts.
        event = self.store._audit(
            c,
            viewer.user_id,
            key,
            "assistance." + record.status,
            {
                "proposal_id": record.proposal_id,
                "proposal_revision": record.revision,
                "status": record.status,
                "application": "blocked",
            },
            ruleset_version="p2-synthetic-v1",
        )
        c.execute(
            t.ai_proposals.insert().values(
                campaign_id=self.store.campaign_id,
                proposal_id=record.proposal_id,
                revision=record.revision,
                owner_id=str(viewer.user_id),
                status=record.status,
                body_json=record.model_dump_json(),
                event_id=event,
            )
        )
        return MutationResult(
            proposal_id=record.proposal_id,
            proposal_revision=record.revision,
            status=record.status,
            campaign_revision=self._revision(c),
        ).model_dump(mode="json")

    def request(self, viewer: GuildViewer, command: RequestAssistance) -> MutationResult:
        command = RequestAssistance.model_validate_json(command.model_dump_json())

        def operation(c: Connection) -> dict[str, Any]:
            self._expect(c, command.expected_campaign_revision)
            self._unpaused(c)
            context = self._context(c, viewer, command.audience, self._revision(c))
            if context.digest != command.context_digest:
                raise WorkflowError("STALE_CONTEXT: refresh authorized context before requesting.")
            record = AssistanceRecord(
                proposal_id=str(uuid4()),
                campaign_id=self.store.campaign_id,
                owner_id=str(viewer.user_id),
                revision=1,
                status="requested",
                context=context,
            )
            return self._append(c, viewer, command.command_key, record)

        result = self.store._write(
            viewer,
            command.command_key,
            "assistance.request",
            {
                "audience": command.audience,
                "context_digest": command.context_digest,
                "task": command.task,
            },
            operation,
            auto_audit=False,
            authorize=lambda c: self._authorize(c, viewer, command.audience),
        )
        return MutationResult.model_validate(result)

    def generate(
        self, viewer: GuildViewer, proposal_id: str, command: GenerateDraft
    ) -> MutationResult:
        command = GenerateDraft.model_validate_json(command.model_dump_json())

        def operation(c: Connection) -> dict[str, Any]:
            record = self._owned(c, viewer, proposal_id)
            self._ready(c, viewer, record, command)
            self._unpaused(c)
            if record.status != "requested":
                raise WorkflowError("ASSISTANCE_STATE: only a requested summary can generate.")
            request = GenerationRequest(context=record.context)
            response = None
            failure = None
            try:
                candidate = self.provider.generate(request)
            except Exception:
                # Never persist or return raw provider errors/credentials/content.
                failure = "PROVIDER_UNAVAILABLE"
            else:
                try:
                    response = GenerationResponse.model_validate_json(candidate.model_dump_json())
                    validate_response(request, response)
                except (ValueError, TypeError, AttributeError):
                    response = None
                    failure = "INVALID_RESPONSE"
            next_record = AssistanceRecord.model_validate(
                record.model_dump()
                | {
                    "revision": record.revision + 1,
                    "status": "failed" if failure else "draft",
                    "response": response,
                    "failure": failure,
                }
            )
            return self._append(c, viewer, command.command_key, next_record)

        result = self.store._write(
            viewer,
            command.command_key,
            "assistance.generate",
            {"proposal_id": proposal_id},
            operation,
            auto_audit=False,
            authorize=lambda c: self._owned_authorize(c, viewer, proposal_id),
        )
        return MutationResult.model_validate(result)

    def _owned_authorize(self, c: Connection, viewer: GuildViewer, proposal_id: str) -> None:
        self._owned(c, viewer, proposal_id)

    def review(self, viewer: GuildViewer, proposal_id: str, command: ReviewDraft) -> MutationResult:
        command = ReviewDraft.model_validate_json(command.model_dump_json())

        def operation(c: Connection) -> dict[str, Any]:
            record = self._owned(c, viewer, proposal_id)
            # Rejection may discard a stale draft while paused. Approval requires
            # the current source snapshot and an unpaused campaign.
            if command.decision == "approve":
                self._ready(c, viewer, record, command)
                self._unpaused(c)
            else:
                self._expect(c, command.expected_campaign_revision)
                if record.revision != command.expected_proposal_revision:
                    raise WorkflowError("STALE_PROPOSAL: reopen the private review.")
            if record.status != "draft":
                raise WorkflowError("ASSISTANCE_STATE: only a draft can be reviewed.")
            next_record = AssistanceRecord.model_validate(
                record.model_dump()
                | {
                    "revision": record.revision + 1,
                    "status": "approved" if command.decision == "approve" else "rejected",
                }
            )
            return self._append(c, viewer, command.command_key, next_record)

        result = self.store._write(
            viewer,
            command.command_key,
            "assistance.review",
            {"proposal_id": proposal_id, "decision": command.decision},
            operation,
            auto_audit=False,
            authorize=lambda c: self._owned_authorize(c, viewer, proposal_id),
        )
        return MutationResult.model_validate(result)

    def get(self, viewer: GuildViewer, proposal_id: str) -> AssistanceView:
        with self.store.transaction() as c:
            record = self._owned(c, viewer, proposal_id)
            return AssistanceView(
                record=record,
                campaign_revision=self._revision(c),
                sources_current=self._sources_current(c, viewer, record),
            )
