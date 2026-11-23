"""Save Handler-owned briefing drafts and disclose the cited facts on a mission offer."""

from typing import Any, cast

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m3_missions import Mission, MissionTerms
from girlframe.scenes.canon import (
    BriefingDraft,
    BriefingSource,
    KnowledgeGrant,
    KnownFact,
    ShadowConsent,
)
from girlframe.services import campaign_time_history as calendar
from girlframe.services import canon_history as history
from girlframe.services.campaign_difficulty import initial_mission_needed, opening
from girlframe.services.canon import CanonService, fact_identity
from girlframe.services.director_canon import capture_consent
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class CanonBriefings:
    def __init__(self, store: OnboardingStore):
        self.store = store
        self.canon = CanonService(store)

    def _principal(self, c: Connection, viewer: GuildViewer) -> str:
        self.canon._access(c, viewer)
        self.canon.handler.authorize(c, viewer)
        principal = self.canon.principal(c, viewer.user_id)
        if principal is None:
            raise WorkflowError("Recover the current Handler before preparing a briefing.")
        return principal

    def draft(self, viewer: GuildViewer, key: str, refs: tuple[str, ...]) -> str:
        refs = tuple(fact_identity(ref) for ref in refs)
        if not refs or len(refs) > 10 or len(set(refs)) != len(refs):
            raise WorkflowError("Include one to ten distinct fact IDs.")

        def operation(c: Connection) -> dict[str, str]:
            self.canon.game.unpaused(c)
            principal = self._principal(c, viewer)
            self._known(c, viewer.user_id, refs)
            draft = BriefingDraft(principal=principal, facts=refs)
            receipt = self.canon._audit(
                c, viewer, key, history.DRAFT, draft.model_dump(mode="json")
            )
            return {"id": receipt}

        def authorize(c: Connection) -> None:
            self._principal(c, viewer)

        result = self.store._write(
            viewer,
            key,
            history.DRAFT,
            {"facts": refs},
            operation,
            auto_audit=False,
            authorize=authorize,
        )
        return cast(str, result["id"])

    def _known(self, c: Connection, owner: int, refs: tuple[str, ...]) -> tuple[KnownFact, ...]:
        current = {fact.fact_id: fact for fact in self.canon.known_in_transaction(c, owner)}
        if any(identity not in current for identity in refs):
            raise WorkflowError("Cite only facts this Handler has learned.")
        if any(current[identity].status != "current" for identity in refs):
            raise WorkflowError(
                "CANON_REVIEW_REQUIRED: a cited fact needs review. Prepare a new briefing."
            )
        return tuple(current[identity] for identity in refs)

    def require_model_sources(self, c: Connection, facts: tuple[KnownFact, ...]) -> None:
        """Keep Activity observation withdrawals in force during separate briefing review."""
        observer = DirectorObservationService(self.store, synthetic=True)

        def require(scene: str, saved: ShadowConsent | None) -> None:
            if saved is None and observer._state(c, scene).activity_epoch is None:
                return  # Manual canon is governed by the separate briefing data opt-in.
            if saved is None or capture_consent(self.store, c, scene, allow_closed=True) != saved:
                raise WorkflowError(
                    "BRIEFING_CONSENT: a selected fact needs current source consent."
                )

        seen_facts: set[str] = set()
        pending = [fact.fact_id for fact in facts]
        while pending:
            identity = pending.pop()
            if identity in seen_facts:
                continue
            source = self.canon._fact(c, identity)
            require(source.window.scene_id, source.shadow_consent)
            seen_facts.add(identity)
            pending.extend(source.depends_on)

        for fact in facts:
            grant_id: str | None = fact.grant_id
            while grant_id is not None:
                raw = c.scalar(
                    calendar.query(self.store.campaign_id, history.GRANT)
                    .where(t.events.c.id == grant_id)
                    .with_only_columns(t.events.c.payload_json)
                )
                if raw is None:
                    raise WorkflowError(
                        "BRIEFING_CONSENT: a selected fact lost its source receipt."
                    )
                grant = KnowledgeGrant.model_validate_json(raw)
                if grant.window is not None:
                    require(grant.window.scene_id, grant.shadow_consent)
                grant_id = grant.source_grant_id

    def drafts(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        campaign = self.store.campaign_id
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            principal = self._principal(c, viewer)
            states = history.statuses(c, campaign)
            return [
                {
                    "id": row["id"],
                    "facts": draft.facts,
                    "needs_review": any(states.get(ref) != "current" for ref in draft.facts),
                }
                for row in c.execute(
                    calendar.query(campaign, history.DRAFT)
                    .where(
                        self._owner(viewer),
                        sa.func.json_extract(t.events.c.payload_json, "$.principal") == principal,
                    )
                    .order_by(t.events.c.seq.desc())
                ).mappings()
                for draft in (BriefingDraft.model_validate_json(row["payload_json"]),)
            ]

    @staticmethod
    def _owner(viewer: GuildViewer) -> sa.ColumnElement[bool]:
        return sa.or_(
            t.events.c.actor_id == str(viewer.user_id),
            sa.func.json_extract(t.events.c.payload_json, "$.approval.handler") == viewer.user_id,
        )

    def record(self, c: Connection, viewer: GuildViewer, draft_id: str) -> BriefingDraft:
        principal = self._principal(c, viewer)
        raw = c.scalar(
            calendar.query(self.store.campaign_id, history.DRAFT)
            .where(t.events.c.id == fact_identity(draft_id), self._owner(viewer))
            .with_only_columns(t.events.c.payload_json)
        )
        if raw is None:
            raise WorkflowError("This briefing draft is unavailable.")
        try:
            draft = BriefingDraft.model_validate_json(raw)
        except ValidationError:
            raise WorkflowError("Recover the original briefing draft.") from None
        if draft.principal != principal:
            raise WorkflowError("This briefing draft belongs to an earlier Handler.")
        return draft

    def prepare(
        self,
        c: Connection,
        viewer: GuildViewer,
        draft_id: str,
        *,
        objective: str | None = None,
        hard_stake: str | None = None,
    ) -> tuple[tuple[KnownFact, ...], MissionTerms | None]:
        draft = self.record(c, viewer, draft_id)
        if approval := draft.approval:
            applied = opening(c, self.store.campaign_id)
            if (
                applied is None
                or applied.plan != approval.plan
                or load_state(c, self.store.campaign_id).revision != approval.game_revision
                or initial_mission_needed(c, self.store.campaign_id) != approval.introductory
            ):
                raise WorkflowError("STALE_BRIEFING: campaign state changed. Prepare a new draft.")
            if (objective, hard_stake) != (approval.objective, approval.hard_stake):
                raise WorkflowError(
                    "Use the exact objective and obstacle the facilitator reviewed."
                )
        facts = self._known(c, viewer.user_id, draft.facts)
        if draft.approval is not None:
            self.require_model_sources(c, facts)
        return facts, draft.approval.terms if draft.approval else None

    def disclose(
        self,
        c: Connection,
        viewer: GuildViewer,
        key: str,
        mission: Mission,
        source_event: str,
        facts: tuple[KnownFact, ...],
    ) -> None:
        saved = calendar.anchor(c, self.store.campaign_id)
        if saved is None:
            raise WorkflowError("Initialize fictional time before including a canon briefing.")
        briefing = BriefingSource(
            mission_id=mission.id,
            offer_event_id=source_event,
            anchor_id=saved[0],
            position=saved[1].position,
        )
        for index, (fact, owner) in enumerate(
            ((fact, owner) for owner in mission.offered_to for fact in facts), start=1
        ):
            grant = KnowledgeGrant(
                fact_id=fact.fact_id,
                recipient=owner,
                principal=f"pilot:{mission.offered_characters[str(owner)]}",
                method="briefed",
                source_grant_id=fact.grant_id,
                briefing=briefing,
            )
            self.canon.save_grant(c, viewer, key, grant, index=index)

    def needs_review(self, c: Connection, mission: Mission) -> bool:
        if not mission.briefing_facts:
            return False
        states = history.statuses(c, self.store.campaign_id)
        return any(states.get(ref) != "current" for ref in mission.briefing_facts)

    def project(self, c: Connection, viewer: GuildViewer, mission: Mission) -> list[dict[str, Any]]:
        if not mission.briefing_facts or self.store.policy.canon_facilitator_id is None:
            return []
        try:
            known = self.canon.known_in_transaction(c, viewer.user_id)
        except WorkflowError:
            return []
        return [
            {"statement": fact.statement, "status": fact.status}
            for fact in known
            if fact.fact_id in mission.briefing_facts
        ]
