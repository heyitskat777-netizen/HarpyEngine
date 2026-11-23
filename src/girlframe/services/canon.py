"""Scene-bound canon, facilitator review, and audience-filtered character knowledge."""

from collections.abc import Callable
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection, RowMapping

from girlframe.database import tables as t
from girlframe.engine.session_zero import SessionZero
from girlframe.scenes.canon import (
    ActivitySource,
    CanonWindow,
    FactView,
    KnowledgeGrant,
    KnownFact,
    LegacyMessageSource,
    Proposal,
    WorldFact,
)
from girlframe.services import campaign_time_history as calendar
from girlframe.services import canon_history as history
from girlframe.services.campaign_difficulty import EVENT, opening
from girlframe.services.director_canon import capture_consent
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

FACT = history.FACT
GRANT = history.GRANT


def fact_identity(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError:
        raise WorkflowError("Use an ID from your canon view.") from None


class CanonService:
    def __init__(self, store: OnboardingStore):
        self.store = store
        self.campaign = store.campaign_id
        self.handler = HandlerService(store)
        self.game = GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer, *, facilitator: bool = False) -> None:
        self.store.guild_member(viewer)
        assigned = self.store.policy.canon_facilitator_id
        if assigned is None:
            raise WorkflowError("Canon is disabled in campaign policy.")
        self.store._membership(c, viewer)
        if facilitator:
            if viewer.user_id != assigned:
                raise WorkflowError("Only the designated canon facilitator can do this.")
            record = opening(c, self.campaign)
            if viewer.user_id == self.handler.current(c)[1].handler_id or (
                record is not None and viewer.user_id == record.handler
            ):
                raise WorkflowError("The canon facilitator and the Handler need separate accounts.")

    def _appointment(self, c: Connection, before: int | None = None) -> str | None:
        query = calendar.query(self.campaign, "campaign.handler_appointed")
        if before is not None:
            query = query.where(t.events.c.seq < before)
        return cast(
            str | None,
            c.scalar(
                query.with_only_columns(t.events.c.id).order_by(t.events.c.seq.desc()).limit(1)
            ),
        )

    def _original_principal(self, c: Connection, owner: int) -> str | None:
        start = (
            c.execute(calendar.query(self.campaign, EVENT).order_by(t.events.c.seq.desc()).limit(1))
            .mappings()
            .first()
        )
        if start is None:
            return None
        record = opening(c, self.campaign)
        if record is None or owner not in record.audience:
            return None
        if owner == record.handler:
            appointment = self._appointment(c, start["seq"])
            return f"handler:{appointment}" if appointment else None
        raw = c.scalar(
            calendar.query(self.campaign, "campaign.session_zero_saved")
            .where(t.events.c.command_key == start["command_key"])
            .with_only_columns(t.events.c.payload_json)
        )
        if raw is None:
            return None
        submission = SessionZero.model_validate_json(raw).submissions.get(str(owner))
        return f"pilot:{submission.sheet.character}" if submission else None

    def principal(self, c: Connection, owner: int) -> str | None:
        state = load_state(c, self.campaign)
        if owner == self.handler.current(c)[1].handler_id:
            appointment = self._appointment(c)
            if appointment is None:
                return None
            if any(x.appointment == appointment for x in state.handler_archives):
                current = state.handler_persona
                if (
                    current is None
                    or current.appointment != appointment
                    or any(x.actor.incarnation == current.id for x in state.handler_archives)
                ):
                    return None
                return f"handler:{appointment}:{current.id}"
            return f"handler:{appointment}"
        if str(owner) in state.sheets:
            ref = self.game.character_binding(c, state, owner, require_current_profile=False)
            return f"pilot:{ref}"
        if any(x.actor.entity == str(owner) for x in state.career_archives):
            return None
        original = self._original_principal(c, owner)
        return original if original and original.startswith("pilot:") else None

    def _participants(self, c: Connection, scene: dict[str, Any]) -> set[int]:
        record = opening(c, self.campaign)
        if record is not None and record.scene == scene["id"]:
            if record.handler != self.handler.current(c)[1].handler_id:
                raise WorkflowError("The opening Handler appointment needs review.")
            return set(record.audience)
        people = set(scene["participants"])
        state = load_state(c, self.campaign)
        cast = next(
            (item for item in state.scene_casts if item.id == scene["id"] and item.open), None
        )
        if cast is None:
            return people
        native = {
            role.controller
            for role in cast.roles
            if role.actor.kind == "pilot"
            and role.actor.entity == str(role.controller)
            and role.controller in people
            and str(role.controller) in state.sheets
            and self.game.character_binding(
                c, state, role.controller, require_current_profile=False
            )
            == role.actor.incarnation
        }
        handler = self.handler.current(c)[1].handler_id
        if (
            handler is not None
            and handler == state.handler
            and any(
                role.actor.kind == "handler"
                and role.actor.entity == str(handler)
                and role.controller == handler
                for role in cast.roles
            )
        ):
            native.add(handler)
        return native

    def current_window(
        self, c: Connection, viewer: GuildViewer, channel: int, *, facilitator: bool
    ) -> CanonWindow:
        self.game.unpaused(c)
        try:
            scene = self.game.scene(c, channel, check_slot=False)
        except WorkflowError:
            raise WorkflowError(
                "Run this command in the Cadre Introduction channel or an open booked scene."
            ) from None
        self.game.scene_unpaused(c, scene["id"])
        current = calendar.anchor(c, self.campaign)
        span = calendar.booking(c, self.campaign, scene["id"])
        if current is None or span is None:
            raise WorkflowError("Schedule this scene before recording canon.")
        anchor_id, anchor = current
        if not span.start.order <= anchor.position.order <= span.end.order:
            raise WorkflowError("The scene's roleplay window is closed or has not begun.")
        if span.requires:
            from girlframe.services.campaign_time import CampaignTimeService

            CampaignTimeService(self.store).require_dependencies(c, span)
        participants = self._participants(c, scene)
        if not facilitator and viewer.user_id not in participants:
            raise WorkflowError(
                "Join this scene as your actual Pilot or Handler before recording canon."
            )
        return CanonWindow(
            scene_id=scene["id"],
            scene_revision=scene["revision"],
            anchor_id=anchor_id,
            position=anchor.position,
        )

    def window(self, viewer: GuildViewer, channel: int | None, *, facilitator: bool) -> CanonWindow:
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self._access(c, viewer, facilitator=facilitator)
            if channel is None:
                raise WorkflowError("Open this command in the scene channel.")
            return self.current_window(c, viewer, channel, facilitator=facilitator)

    def window_for_scene(
        self, viewer: GuildViewer, scene_id: str, *, facilitator: bool = False
    ) -> CanonWindow:
        """Resolve an Activity scene using only HarpyEngine's saved scene binding."""
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self._access(c, viewer, facilitator=facilitator)
            channel = self._channel(c, fact_identity(scene_id))
            return self.current_window(c, viewer, channel, facilitator=facilitator)

    def _channel(self, c: Connection, scene_id: str) -> int:
        table = t.m2["m2_scenes"]
        channel = c.scalar(
            sa.select(table.c.channel_id).where(
                table.c.campaign_id == self.campaign,
                table.c.id == scene_id,
                table.c.open.is_(True),
            )
        )
        if channel is None:
            raise WorkflowError("STALE_CANON: the original scene is closed.")
        return int(channel)

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        kind: str,
        payload: dict[str, Any],
        apply: Callable[[Connection], str],
        *,
        facilitator: bool,
    ) -> str:
        result = self.store._write(
            viewer,
            key,
            kind,
            payload,
            lambda c: {"receipt": apply(c)},
            authorize=lambda c: self._access(c, viewer, facilitator=facilitator),
            auto_audit=False,
        )
        return cast(str, result["receipt"])

    def _in_window(
        self,
        viewer: GuildViewer,
        key: str,
        kind: str,
        expected: CanonWindow,
        payload: dict[str, Any],
        apply: Callable[[Connection, int], str],
        *,
        facilitator: bool,
    ) -> str:
        def operation(c: Connection) -> str:
            channel = self._channel(c, expected.scene_id)
            current = self.current_window(c, viewer, channel, facilitator=facilitator)
            if expected.scene_revision is None:
                current = current.model_copy(update={"scene_revision": None})
            if current != expected:
                raise WorkflowError("STALE_CANON: reopen the scene at its current time.")
            return apply(c, channel)

        return self._write(
            viewer,
            key,
            kind,
            {"window": expected.model_dump(mode="json"), **payload},
            operation,
            facilitator=facilitator,
        )

    def _audit(
        self,
        c: Connection,
        viewer: GuildViewer,
        key: str,
        kind: str,
        payload: dict[str, Any],
        *,
        index: int = 0,
    ) -> str:
        return self.store._audit(
            c, viewer.user_id, key, kind, payload, event_index=index, ruleset_version="canon-v1"
        )

    def _fact(self, c: Connection, fact_id: str) -> WorldFact:
        raw = c.scalar(
            calendar.query(self.campaign, FACT)
            .where(t.events.c.id == fact_id)
            .with_only_columns(t.events.c.payload_json)
        )
        if raw is None:
            raise WorkflowError("That fact is unavailable in this campaign.")
        return WorldFact.model_validate_json(raw)

    def _validate_refs(self, c: Connection, refs: tuple[str, ...]) -> None:
        if len(set(refs)) != len(refs):
            raise WorkflowError("Cite each fact only once.")
        if refs:
            states = history.statuses(c, self.campaign)
            if any(states.get(identity) != "current" for identity in refs):
                raise WorkflowError("A cited fact is unavailable or needs review.")

    def establish(
        self,
        viewer: GuildViewer,
        key: str,
        expected: CanonWindow,
        statement: str,
        *,
        depends_on: tuple[str, ...] = (),
        public: bool = False,
    ) -> str:
        try:
            fact = WorldFact(
                window=expected, statement=statement, depends_on=depends_on, public=public
            )
        except ValidationError:
            raise WorkflowError(
                "Enter a setting fact of 1–600 characters and valid fact IDs."
            ) from None

        def apply(c: Connection, channel: int) -> str:
            self._validate_refs(c, fact.depends_on)
            saved = fact.model_copy(
                update={"shadow_consent": capture_consent(self.store, c, expected.scene_id)}
            )
            return self._audit(c, viewer, key, FACT, saved.model_dump(mode="json"))

        payload: dict[str, Any] = {"statement": fact.statement}
        if fact.public:
            payload["public"] = True
        if fact.depends_on:
            payload["depends_on"] = fact.depends_on
        return self._in_window(
            viewer, key, "canon.establish", expected, payload, apply, facilitator=True
        )

    def correct(
        self,
        viewer: GuildViewer,
        key: str,
        fact_id: str,
        statement: str,
        *,
        depends_on: tuple[str, ...] = (),
    ) -> str:
        fact_id = fact_identity(fact_id)

        def apply(c: Connection) -> str:
            self.game.unpaused(c)
            previous = self._fact(c, fact_id)
            self.game.scene_unpaused(c, previous.window.scene_id)
            states = history.statuses(c, self.campaign)
            if states[fact_id] == "superseded":
                raise WorkflowError(
                    "That fact already has a correction. Review the current record."
                )
            self._validate_refs(c, depends_on)
            # A correction must not invalidate the evidence it relies on.
            parents = list(depends_on)
            checked = set()
            while parents:
                identity = parents.pop()
                if identity == fact_id:
                    raise WorkflowError(
                        "A correction needs sources independent of the replaced fact."
                    )
                if identity not in checked:
                    checked.add(identity)
                    parents.extend(self._fact(c, identity).depends_on)
            current = calendar.anchor(c, self.campaign)
            if current is None:
                raise WorkflowError("The campaign calendar is unavailable.")
            try:
                fact = WorldFact(
                    window=CanonWindow(
                        scene_id=previous.window.scene_id,
                        anchor_id=current[0],
                        position=current[1].position,
                    ),
                    statement=statement,
                    public=previous.public,
                    supersedes=fact_id,
                    depends_on=depends_on,
                    shadow_consent=capture_consent(self.store, c, previous.window.scene_id),
                )
            except ValidationError:
                raise WorkflowError(
                    "Enter a setting fact of 1–600 characters and valid fact IDs."
                ) from None
            return self._audit(c, viewer, key, FACT, fact.model_dump(mode="json"))

        return self._write(
            viewer,
            key,
            "canon.correct",
            {"supersedes": fact_id, "statement": statement, "depends_on": depends_on},
            apply,
            facilitator=True,
        )

    def propose_activity(
        self,
        viewer: GuildViewer,
        submission_id: str,
        expected: CanonWindow,
        statement: str,
        *,
        depends_on: tuple[str, ...] = (),
    ) -> str:
        try:
            source = ActivitySource(submission_id=submission_id)
            proposal = Proposal(
                window=expected, statement=statement, source=source, depends_on=depends_on
            )
        except ValidationError:
            raise WorkflowError(
                "Provide a submission ID, a statement of 1–600 characters, and valid fact IDs."
            ) from None
        if expected.scene_revision is None:
            raise WorkflowError("Refresh the current Activity scene before submitting.")
        key = f"activity.canon:{viewer.user_id}:{source.submission_id}"
        data = proposal.model_dump(mode="json")

        def apply(c: Connection, channel: int) -> str:
            known = {
                fact.fact_id
                for fact in self.known_in_transaction(c, viewer.user_id)
                if fact.status == "current"
            }
            if (
                len(set(proposal.depends_on)) != len(proposal.depends_on)
                or not set(proposal.depends_on) <= known
            ):
                raise WorkflowError("Cite distinct facts your character currently knows.")
            saved = proposal.model_copy(
                update={"shadow_consent": capture_consent(self.store, c, expected.scene_id)}
            )
            return self._audit(c, viewer, key, history.PROPOSAL, saved.model_dump(mode="json"))

        return self._in_window(
            viewer, key, "canon.propose", expected, data, apply, facilitator=False
        )

    def _proposals(
        self, c: Connection, viewer: GuildViewer, *, facilitator: bool
    ) -> list[dict[str, Any]]:
        query = calendar.query(self.campaign, history.PROPOSAL).where(
            sa.func.json_extract(t.events.c.payload_json, "$.source.message_id").is_(None)
        )
        if not facilitator:
            query = query.where(t.events.c.actor_id == str(viewer.user_id))
        reviews = {
            data["proposal_id"]: data["decision"]
            for _, data in calendar.history(c, self.campaign, history.REVIEW)
        }
        return [
            {
                "id": row["id"],
                "created_utc": row["created_utc"],
                "status": reviews.get(row["id"], "pending"),
                **Proposal.model_validate_json(row["payload_json"]).model_dump(
                    mode="json", exclude={"shadow_consent"}
                ),
            }
            for row in c.execute(query.order_by(t.events.c.seq.desc())).mappings()
        ]

    def proposals(self, viewer: GuildViewer, *, facilitator: bool = False) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self._access(c, viewer, facilitator=facilitator)
            return self._proposals(c, viewer, facilitator=facilitator)

    def review(
        self,
        viewer: GuildViewer,
        key: str,
        proposal_id: str,
        *,
        approve: bool,
        public: bool = False,
    ) -> str:
        proposal_id = fact_identity(proposal_id)

        def apply(c: Connection) -> str:
            self.game.unpaused(c)
            raw = c.scalar(
                calendar.query(self.campaign, history.PROPOSAL)
                .where(t.events.c.id == proposal_id)
                .with_only_columns(t.events.c.payload_json)
            )
            reviewed = c.scalar(
                calendar.query(self.campaign, history.REVIEW)
                .where(
                    sa.func.json_extract(t.events.c.payload_json, "$.proposal_id") == proposal_id
                )
                .with_only_columns(t.events.c.id)
            )
            if raw is None or reviewed is not None:
                raise WorkflowError("This proposal is unavailable or already reviewed.")
            proposal = Proposal.model_validate_json(raw)
            fact_id = None
            if approve:
                if isinstance(proposal.source, LegacyMessageSource):
                    raise WorkflowError(
                        "Submit this declaration in the Activity before approving it."
                    )
                channel = self._channel(c, proposal.window.scene_id)
                window = self.current_window(c, viewer, channel, facilitator=True)
                self._validate_refs(c, proposal.depends_on)
                consent = capture_consent(self.store, c, window.scene_id)
                fact = WorldFact(
                    window=window,
                    statement=proposal.statement,
                    public=public,
                    depends_on=proposal.depends_on,
                    proposal_id=proposal_id,
                    shadow_consent=consent if consent == proposal.shadow_consent else None,
                )
                fact_id = self._audit(c, viewer, key, FACT, fact.model_dump(mode="json"), index=1)
            receipt = self._audit(
                c,
                viewer,
                key,
                history.REVIEW,
                {
                    "proposal_id": proposal_id,
                    "decision": "approved" if approve else "declined",
                    "fact_id": fact_id,
                },
            )
            return fact_id or receipt

        return self._write(
            viewer,
            key,
            "canon.review",
            {"proposal_id": proposal_id, "approve": approve, "public": public},
            apply,
            facilitator=True,
        )

    def _grants_for(
        self, c: Connection, recipient: int, principal: str
    ) -> list[tuple[RowMapping, KnowledgeGrant]]:
        query = history.grants(self.campaign, recipient).where(
            sa.or_(
                sa.func.json_extract(t.events.c.payload_json, "$.principal") == principal,
                sa.func.json_extract(t.events.c.payload_json, "$.principal").is_(None),
            )
        )
        original = None
        result = []
        for row in c.execute(query.order_by(t.events.c.seq)).mappings():
            grant = KnowledgeGrant.model_validate_json(row["payload_json"])
            if grant.principal is None:
                original = original or self._original_principal(c, recipient)
                if principal != original:
                    continue
            result.append((row, grant))
        return result

    def save_grant(
        self,
        c: Connection,
        viewer: GuildViewer,
        key: str,
        grant: KnowledgeGrant,
        *,
        index: int = 0,
    ) -> str | None:
        assert grant.principal is not None
        if any(
            x.fact_id == grant.fact_id
            for _, x in self._grants_for(c, grant.recipient, grant.principal)
        ):
            return None
        return self._audit(c, viewer, key, GRANT, grant.model_dump(mode="json"), index=index)

    def witness(
        self, viewer: GuildViewer, key: str, expected: CanonWindow, fact_id: str, pilot: int
    ) -> str:
        fact_id = fact_identity(fact_id)

        def apply(c: Connection, channel: int) -> str:
            scene = self.game.scene(c, channel, check_slot=False)
            current = self.handler.current(c)[1].handler_id
            participants = self._participants(c, scene)
            principal = (
                self.principal(c, pilot) if pilot in participants and pilot != current else None
            )
            if principal is None or not self.handler._member(c, pilot):
                raise WorkflowError("Choose a participating Pilot as the witness.")
            fact = self._fact(c, fact_id)
            if fact.window.position.order > expected.position.order:
                raise WorkflowError("That fact is unavailable to witness in this scene.")
            self._validate_refs(c, (fact_id,))
            grant = KnowledgeGrant(
                window=expected,
                fact_id=fact_id,
                recipient=pilot,
                method="witnessed",
                principal=principal,
                shadow_consent=capture_consent(self.store, c, expected.scene_id),
            )
            receipt = self.save_grant(c, viewer, key, grant)
            if receipt is None:
                raise WorkflowError("That character already knows this fact.")
            return receipt

        return self._in_window(
            viewer,
            key,
            "canon.witness",
            expected,
            {"fact_id": fact_id, "pilot": pilot},
            apply,
            facilitator=True,
        )

    def report(self, viewer: GuildViewer, key: str, expected: CanonWindow, fact_id: str) -> str:
        fact_id = fact_identity(fact_id)

        def apply(c: Connection, channel: int) -> str:
            handler = self.handler.current(c)[1].handler_id
            principal = self.principal(c, viewer.user_id)
            sources = (
                self._grants_for(c, viewer.user_id, principal) if principal is not None else []
            )
            source = next(
                (
                    row["id"]
                    for row, grant in sources
                    if grant.fact_id == fact_id
                    and grant.method in ("witnessed", "told")
                    and grant.learned_at.order <= expected.position.order
                ),
                None,
            )
            if source is None or handler == viewer.user_id:
                raise WorkflowError("You do not have a witness record or NPC lead for that fact.")
            scene = self.game.scene(c, channel, check_slot=False)
            participants = self._participants(c, scene)
            receiver = (
                self.principal(c, handler)
                if handler is not None and handler in participants
                else None
            )
            if receiver is None or handler is None or not self.handler._member(c, handler):
                raise WorkflowError(
                    "The current Handler must take part in this scene to receive reports."
                )
            self._validate_refs(c, (fact_id,))
            grant = KnowledgeGrant(
                window=expected,
                fact_id=fact_id,
                recipient=handler,
                method="reported",
                source_grant_id=source,
                principal=receiver,
                shadow_consent=capture_consent(self.store, c, expected.scene_id),
            )
            receipt = self.save_grant(c, viewer, key, grant)
            if receipt is None:
                raise WorkflowError("That character already knows this fact.")
            return receipt

        return self._in_window(
            viewer,
            key,
            "canon.report",
            expected,
            {"fact_id": fact_id},
            apply,
            facilitator=False,
        )

    def world(self, viewer: GuildViewer, *, public: bool = False) -> tuple[FactView, ...]:
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self._access(c, viewer, facilitator=not public)
            query = calendar.query(self.campaign, FACT)
            if public:
                query = query.where(sa.func.json_extract(t.events.c.payload_json, "$.public") == 1)
            states = history.statuses(c, self.campaign)
            return tuple(
                FactView(
                    fact_id=row["id"],
                    statement=fact.statement,
                    established_at=fact.window.position,
                    status=states[row["id"]],
                    supersedes=fact.supersedes,
                    depends_on=() if public else fact.depends_on,
                )
                for row in c.execute(query.order_by(t.events.c.seq)).mappings()
                for fact in (WorldFact.model_validate_json(row["payload_json"]),)
            )

    def known_in_transaction(self, c: Connection, owner: int) -> tuple[KnownFact, ...]:
        principal = self.principal(c, owner)
        if principal is None:
            raise WorkflowError("Character knowledge is unavailable to you.")
        states = history.statuses(c, self.campaign)
        return tuple(
            KnownFact(
                fact_id=grant.fact_id,
                statement=self._fact(c, grant.fact_id).statement,
                grant_id=row["id"],
                method=grant.method,
                learned_at=grant.learned_at,
                status=states[grant.fact_id],
            )
            for row, grant in self._grants_for(c, owner, principal)
        )

    def known(self, viewer: GuildViewer) -> tuple[KnownFact, ...]:
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self._access(c, viewer)
            return self.known_in_transaction(c, viewer.user_id)
