"""Activity workflow for durable AI drafts, human review, and normal mission offers."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal, cast
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection, RowMapping

from girlframe.ai.briefing import (
    PROMPT_VERSION,
    BriefingContext,
    BriefingFact,
    BriefingGateway,
    BriefingPolicy,
    BriefingProviderError,
    GatewayResult,
)
from girlframe.ai.openai_briefing import OpenAIBriefingGateway
from girlframe.database import tables as t
from girlframe.engine.m2 import Model
from girlframe.scenes.canon import BriefingApproval, BriefingDraft, FactRefs
from girlframe.services import campaign_time_history as calendar
from girlframe.services import canon_history
from girlframe.services.ai_attempts import ATTEMPT_SECONDS as ATTEMPT_SECONDS
from girlframe.services.ai_attempts import BRIEFING_RESERVATION as RESERVATION
from girlframe.services.ai_attempts import reserve_attempt
from girlframe.services.campaign_difficulty import initial_mission_needed, opening
from girlframe.services.canon import fact_identity
from girlframe.services.canon_briefings import CanonBriefings
from girlframe.services.m2_state import load_state
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

REQUEST = "ai.mission_briefing_requested"
RESULT = "ai.mission_briefing_result"
REVIEW = "ai.mission_briefing_reviewed"


class BriefingRequest(Model):
    principal: str
    refs: FactRefs
    snapshot: str
    model: str
    prompt_version: str


@dataclass(frozen=True)
class Snapshot:
    principal: str
    plan: str
    game_revision: int
    context: BriefingContext

    @property
    def fingerprint(self) -> str:
        content = json.dumps(
            {
                "principal": self.principal,
                "plan": self.plan,
                "game_revision": self.game_revision,
                "context": self.context.model_dump(mode="json"),
            },
            sort_keys=True,
        )
        return hashlib.sha256(content.encode()).hexdigest()


class DraftMissionBriefingService:
    def __init__(self, store: OnboardingStore, gateway: BriefingGateway | None = None):
        self.store = store
        self.campaign = store.campaign_id
        self.briefings = CanonBriefings(store)
        self.canon = self.briefings.canon
        self.missions = MissionService(store)
        self.gateway = gateway if gateway is not None else OpenAIBriefingGateway()

    def _policy(self) -> BriefingPolicy:
        policy = self.store.policy.ai_mission_briefing
        if policy is None:
            raise WorkflowError("AI mission drafting is disabled in campaign policy.")
        return policy

    def _snapshot(self, c: Connection, owner: int, refs: tuple[str, ...]) -> Snapshot:
        record = opening(c, self.campaign)
        if record is None or not record.goals.strip():
            raise WorkflowError(
                "Complete Session Zero with approved goals before using AI drafting."
            )
        state = load_state(c, self.campaign)
        if (
            owner != self.canon.handler.current(c)[1].handler_id
            or owner != state.handler
            or not self.canon.handler._member(c, owner)
        ):
            raise WorkflowError("The original Handler appointment is no longer current.")
        principal = self.canon.principal(c, owner)
        if principal is None:
            raise WorkflowError("Recover the current Handler before preparing a briefing.")
        introductory = initial_mission_needed(c, self.campaign)
        facts = self.briefings._known(c, owner, refs)
        self.briefings.require_model_sources(c, facts)
        return Snapshot(
            principal,
            record.plan,
            state.revision,
            BriefingContext(
                goals=record.goals,
                difficulty=record.difficulty,
                introductory=introductory,
                facts=tuple(
                    BriefingFact(id=fact.fact_id, statement=fact.statement) for fact in facts
                ),
            ),
        )

    def _unpaused(self, c: Connection) -> None:
        self.canon.game.unpaused(c)
        record = opening(c, self.campaign)
        if record is not None and initial_mission_needed(c, self.campaign):
            self.canon.game.scene_unpaused(c, record.scene)

    def _audit(
        self,
        c: Connection,
        viewer: GuildViewer,
        key: str,
        kind: str,
        body: dict[str, Any],
        *,
        index: int = 0,
        event_id: str | None = None,
    ) -> str:
        return self.store._audit(
            c,
            viewer.user_id,
            key,
            kind,
            body,
            event_index=index,
            event_id=event_id,
            ruleset_version=PROMPT_VERSION,
        )

    def queue(self, viewer: GuildViewer, request_id: str, fact_ids: tuple[str, ...] = ()) -> str:
        request_id = fact_identity(request_id)
        if len(fact_ids) > 10:
            raise WorkflowError("Select at most ten facts to send to the model.")
        refs = tuple(fact_identity(fact_id) for fact_id in fact_ids)
        if len(set(refs)) != len(refs):
            raise WorkflowError("Select each briefing fact once.")
        key = f"activity.ai-briefing:{viewer.user_id}:{request_id}"

        def authorize(c: Connection) -> None:
            self.briefings._principal(c, viewer)

        def operation(c: Connection) -> dict[str, str]:
            policy = self._policy()
            self.missions.access.authorize(c, viewer, "missions")
            self._unpaused(c)
            snapshot = self._snapshot(c, viewer.user_id, refs)
            request = BriefingRequest(
                principal=snapshot.principal,
                refs=refs,
                snapshot=snapshot.fingerprint,
                model=policy.model,
                prompt_version=PROMPT_VERSION,
            )
            return {"id": self._audit(c, viewer, key, REQUEST, request.model_dump(mode="json"))}

        result = self.store._write(
            viewer,
            key,
            REQUEST,
            {"facts": refs},
            operation,
            authorize=authorize,
            auto_audit=False,
        )
        return cast(str, result["id"])

    def _request(self, c: Connection, identity: str) -> tuple[int, BriefingRequest]:
        row = (
            c.execute(calendar.query(self.campaign, REQUEST).where(t.events.c.id == identity))
            .mappings()
            .first()
        )
        if row is None:
            raise WorkflowError("This briefing request is unavailable.")
        return int(row["actor_id"]), BriefingRequest.model_validate_json(row["payload_json"])

    def _authorize_reader(
        self,
        c: Connection,
        viewer: GuildViewer,
        owner: int,
        request: BriefingRequest,
    ) -> None:
        if viewer.user_id == self.store.policy.canon_facilitator_id:
            self.canon._access(c, viewer, facilitator=True)
        elif viewer.user_id != owner or self.briefings._principal(c, viewer) != request.principal:
            raise WorkflowError("This briefing request is unavailable.")

    def _latest(self, c: Connection, identity: str) -> RowMapping | None:
        return (
            c.execute(
                calendar.query(self.campaign, RESERVATION, RESULT, REVIEW)
                .where(sa.func.json_extract(t.events.c.payload_json, "$.request_id") == identity)
                .order_by(t.events.c.seq.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )

    def _view(
        self,
        c: Connection,
        identity: str,
        request: BriefingRequest,
        latest: RowMapping | None,
    ) -> dict[str, Any]:
        view: dict[str, Any] = {
            "id": identity,
            "status": "queued",
            "fact_ids": list(request.refs),
            "model": request.model,
            "prompt_version": request.prompt_version,
        }
        if latest is None:
            return view
        data = json.loads(latest["payload_json"])
        if latest["kind"] == RESERVATION:
            over = self.store.clock() >= data["expires_at"]
            return view | {"status": "interrupted" if over else "running"}
        if latest["kind"] == REVIEW:
            result = c.scalar(
                calendar.query(self.campaign, RESULT)
                .where(t.events.c.id == data["result_id"])
                .with_only_columns(t.events.c.payload_json)
            )
            saved = json.loads(result) if result else {}
            return view | {
                "status": data["status"],
                "briefing_draft": data["briefing_draft"],
                "proposal": saved.get("proposal"),
            }
        return view | {
            "status": data["status"],
            "result_id": latest["id"],
            **{key: data[key] for key in ("proposal", "error") if key in data},
        }

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        identity = fact_identity(identity)
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self.canon._access(c, viewer)
            owner, request = self._request(c, identity)
            self._authorize_reader(c, viewer, owner, request)
            return self._view(c, identity, request, self._latest(c, identity))

    def list(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            facilitator = viewer.user_id == self.store.policy.canon_facilitator_id
            self.canon._access(c, viewer, facilitator=facilitator)
            query = calendar.query(self.campaign, REQUEST)
            if facilitator:
                try:
                    principal = self.briefings._principal(c, viewer)
                except WorkflowError:
                    principal = None
            else:
                principal = self.briefings._principal(c, viewer)
                query = query.where(
                    t.events.c.actor_id == str(viewer.user_id),
                    sa.func.json_extract(t.events.c.payload_json, "$.principal") == principal,
                )
            return [
                self._view(
                    c,
                    row["id"],
                    BriefingRequest.model_validate_json(row["payload_json"]),
                    self._latest(c, row["id"]),
                )
                | {
                    "own_request": row["actor_id"] == str(viewer.user_id)
                    and principal is not None
                    and json.loads(row["payload_json"])["principal"] == principal,
                }
                for row in c.execute(query.order_by(t.events.c.seq.desc()).limit(25)).mappings()
            ]

    def _unchanged(self, c: Connection, owner: int, request: BriefingRequest) -> Snapshot | None:
        try:
            snapshot = self._snapshot(c, owner, request.refs)
        except WorkflowError:
            return None
        if snapshot.fingerprint != request.snapshot or request.prompt_version != PROMPT_VERSION:
            return None
        return snapshot

    def _save_result(
        self,
        c: Connection,
        viewer: GuildViewer,
        identity: str,
        request: BriefingRequest,
        status: Literal["ready", "failed", "stale"],
        *,
        result: GatewayResult | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"request_id": identity, "status": status}
        if result is not None:
            body.update(result.model_dump(mode="json", exclude={"proposal"}))
            if status == "ready":
                body["proposal"] = result.proposal.model_dump(mode="json")
        if error is not None:
            body["error"] = error
        self._audit(c, viewer, f"ai-briefing.result:{identity}", RESULT, body)
        return self._view(c, identity, request, self._latest(c, identity))

    def run(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        identity = fact_identity(identity)
        with self.store.transaction() as c:
            policy = self._policy()
            principal = self.briefings._principal(c, viewer)
            owner, request = self._request(c, identity)
            if owner != viewer.user_id or request.principal != principal:
                raise WorkflowError("Only the requesting Handler can run this draft.")
            latest = self._latest(c, identity)
            if latest is not None:
                return self._view(c, identity, request, latest)
            self.missions.access.authorize(c, viewer, "missions")
            self._unpaused(c)
            snapshot = self._unchanged(c, owner, request)
            if snapshot is None or policy.model != request.model:
                return self._save_result(c, viewer, identity, request, "stale")
            attempt = reserve_attempt(
                c,
                self.store,
                viewer,
                identity,
                policy,
                kind=RESERVATION,
                key=f"ai-briefing.reserve:{identity}",
                prompt_version=PROMPT_VERSION,
            )

        result = None
        failure = None
        try:
            result = self.gateway.generate(request.model, snapshot.context, identity)
            proposal = result.proposal
            if (
                len(proposal.fact_ids) != len(request.refs)
                or set(proposal.fact_ids) != set(request.refs)
                or (proposal.hard_stake is not None) != snapshot.context.needs_obstacle
            ):
                failure = "invalid_proposal"
        except BriefingProviderError as error:
            failure = error.code

        with self.store.transaction() as c:
            latest = self._latest(c, identity)
            if latest is None or latest["id"] != attempt:
                return self._view(c, identity, request, latest)
            if self.store.clock() >= json.loads(latest["payload_json"])["expires_at"]:
                return self._view(c, identity, request, latest)
            try:
                self._unpaused(c)
            except WorkflowError:
                return self._save_result(c, viewer, identity, request, "stale", result=result)
            if self._unchanged(c, owner, request) is None:
                return self._save_result(c, viewer, identity, request, "stale", result=result)
            if failure is not None:
                return self._save_result(
                    c, viewer, identity, request, "failed", result=result, error=failure
                )
            return self._save_result(c, viewer, identity, request, "ready", result=result)

    def review(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        result_id: str,
        *,
        approve: bool,
    ) -> dict[str, Any]:
        identity, result_id = fact_identity(identity), fact_identity(result_id)

        def operation(c: Connection) -> dict[str, Any]:
            self._unpaused(c)
            owner, request = self._request(c, identity)
            latest = self._latest(c, identity)
            if latest is None or latest["kind"] != RESULT or latest["id"] != result_id:
                raise WorkflowError("STALE_BRIEFING: reopen the current draft before reviewing.")
            stored = json.loads(latest["payload_json"])
            if stored["status"] != "ready":
                raise WorkflowError("Only a ready briefing can be reviewed.")
            draft_id = str(uuid4()) if approve else None
            receipt = self._audit(
                c,
                viewer,
                key,
                REVIEW,
                {
                    "request_id": identity,
                    "result_id": result_id,
                    "status": "approved" if approve else "declined",
                    "briefing_draft": draft_id,
                },
            )
            if approve:
                snapshot = self._unchanged(c, owner, request)
                if snapshot is None:
                    raise WorkflowError(
                        "STALE_BRIEFING: the campaign changed. Prepare a new draft."
                    )
                from girlframe.ai.briefing import DraftText

                proposal = DraftText.model_validate_json(json.dumps(stored["proposal"]))
                draft = BriefingDraft(
                    principal=snapshot.principal,
                    facts=request.refs,
                    approval=BriefingApproval(
                        handler=owner,
                        review_id=receipt,
                        plan=snapshot.plan,
                        game_revision=snapshot.game_revision,
                        introductory=snapshot.context.introductory,
                        objective=proposal.objective,
                        hard_stake=proposal.hard_stake,
                        terms=proposal.terms,
                    ),
                )
                self._audit(
                    c,
                    viewer,
                    key,
                    canon_history.DRAFT,
                    draft.model_dump(mode="json"),
                    index=1,
                    event_id=draft_id,
                )
            return self._view(c, identity, request, self._latest(c, identity))

        return self.store._write(
            viewer,
            key,
            REVIEW,
            {"id": identity, "result": result_id, "approve": approve},
            operation,
            auto_audit=False,
            authorize=lambda c: self.canon._access(c, viewer, facilitator=True),
        )

    def offer(
        self,
        viewer: GuildViewer,
        key: str,
        briefing_draft: str,
        players: tuple[int, ...],
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            draft = self.briefings.record(c, viewer, briefing_draft)
            if draft.approval is None:
                raise WorkflowError("Choose a facilitator-approved AI briefing.")
        return self.missions.offer(
            viewer,
            key,
            draft.approval.objective,
            players,
            hard_stake=draft.approval.hard_stake,
            briefing_draft=briefing_draft,
        )
