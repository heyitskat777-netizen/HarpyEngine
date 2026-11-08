"""Owned actual medical waking and durable compulsory Girl Play exchange after Defeat."""

import json
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_medical as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_medical import Care, Exchange
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access, load_registry
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KIND = "defeat_medical_wake"


class MedicalService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _row(self, c: Connection, identity: str, *, first: bool = False) -> dict[str, Any]:
        table = t.m3["m3_required_work"]
        query = sa.select(table).where(
            table.c.campaign_id == self.store.campaign_id,
            table.c.kind == KIND,
            table.c.id == identity,
        )
        row = (
            c.execute(
                query.order_by(table.c.revision if first else table.c.revision.desc()).limit(1)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise WorkflowError("This original medical recovery is unavailable.")
        return dict(row)

    def _source(
        self, c: Connection, identity: str
    ) -> tuple[dict[str, Any], dict[str, Any], ActorRef]:
        row, original = self._row(c, identity), self._row(c, identity, first=True)
        body, start = json.loads(row["body_json"]), json.loads(original["body_json"])
        try:
            actor = ActorRef.model_validate_json(json.dumps(start["owner"]))
            if (
                actor.kind != "pilot"
                or original["revision"] != 1
                or original["owner_id"] != actor.entity
                or original["subject_id"] != actor.entity
                or start["character"] != actor.incarnation
                or not original["campaign_context"]
                or any(original[k] is not None for k in ("scene_id", "mission_id", "off_duty_id"))
                or any(
                    body.get(k) != start.get(k)
                    for k in ("owner", "character", "source_action", "source_pdf")
                )
            ):
                raise ValueError()
            action = self.game.action(c, start["source_action"])
            if action["data"]["play"] != "defeat" or action["actor_id"] != actor.entity:
                raise ValueError()
            index = next(
                (
                    i
                    for i, x in enumerate(action["data"].get("defeat_followups", []))
                    if x["kind"] == "medical_wake" and x["owner"] == start["owner"]
                ),
                None,
            )
            expected = str(
                uuid5(NAMESPACE_URL, "girlframe:defeat:" + action["id"] + ":" + str(index))
            )
            if index is None or expected != identity:
                raise ValueError()
            responses, choices = t.m2["m2_responses"], t.m2["m2_choices"]
            answer = c.scalar(
                sa.select(responses.c.answer_json)
                .join(
                    choices,
                    sa.and_(
                        responses.c.campaign_id == choices.c.campaign_id,
                        responses.c.choice_id == choices.c.id,
                    ),
                )
                .where(
                    responses.c.campaign_id == self.store.campaign_id,
                    responses.c.event_id == original["event_id"],
                    responses.c.actor_id == actor.entity,
                    choices.c.action_id == action["id"],
                    choices.c.kind == "defeat_select",
                )
            )
            if (
                answer is None
                or "handler_rescue_swap_girl_play_on_waking" not in json.loads(answer)["options"]
            ):
                raise ValueError()
            history = t.m2["m2_state_history"]
            raw = c.scalar(
                sa.select(history.c.body_json).where(
                    history.c.campaign_id == self.store.campaign_id,
                    history.c.event_id == original["event_id"],
                )
            )
            proof = GameState.model_validate_json(raw) if raw else None
            if (
                proof is None
                or actor.entity not in proof.sheets
                or proof.sheets[actor.entity].medical_state != "unconscious_injured"
                or not any(x.actor == actor and x.incapacitated for x in proof.placements)
            ):
                raise ValueError()
        except (ValueError, KeyError, StopIteration):
            raise WorkflowError(
                "SOURCE_MEDICAL_MISSING: recover the actual original Defeat injury."
            ) from None
        if row["revision"] > 1:
            current = (
                c.execute(
                    sa.select(t.events).where(
                        t.events.c.campaign_id == self.store.campaign_id,
                        t.events.c.id == row["event_id"],
                    )
                )
                .mappings()
                .first()
            )
            metadata = json.loads(current["payload_json"]) if current else {}
            archived = body.get("resolution") == "original_character_career_ended"
            if archived:
                state = load_state(c, self.store.campaign_id)
                archive = next(
                    (
                        x
                        for x in state.career_archives
                        if x.id == body.get("career_archive")
                        and x.actor == actor
                        and x.source_event == row["event_id"]
                    ),
                    None,
                )
                if archive is None or row["state"] != "resolved":
                    raise WorkflowError(
                        "SOURCE_MEDICAL_CAREER_MISSING: recover the original ending."
                    )
            else:
                stage = body.get("stage", "need_care")
                expected_kind = {
                    "need_care": "m3.medical_care_declined",
                    "awaiting_confirmation": "m3.medical_care_proposed",
                    "choose_play": "m3.medical_wake_confirmed",
                    "standards_setup": "m3.medical_standards_required",
                    "complete": "m3.medical_play_exchanged",
                }.get(stage)
                expected_owner = (
                    actor.entity
                    if stage in ("awaiting_confirmation", "standards_setup", "complete")
                    else str(body.get("reviewer"))
                )
                if (
                    current is None
                    or current["kind"] != expected_kind
                    or current["actor_id"] != expected_owner
                    or metadata.get("work_id") != identity
                ):
                    raise WorkflowError(
                        "SOURCE_MEDICAL_PHASE_MISSING: recover the actual owned transition."
                    )
                if stage in ("need_care", "awaiting_confirmation", "choose_play"):
                    care = Care.model_validate_json(json.dumps(body["care"]))
                    if metadata.get("care_sha256") != fingerprint(care):
                        raise WorkflowError(
                            "SOURCE_MEDICAL_CARE_MISSING: recover the exact care proposal."
                        )
                elif stage in ("standards_setup", "complete"):
                    selected = Exchange.model_validate_json(
                        json.dumps(
                            body["pending_exchange" if stage == "standards_setup" else "exchange"]
                        )
                    )
                    if metadata.get("exchange_sha256") != fingerprint(selected) or (
                        stage == "complete" and row["state"] != "resolved"
                    ):
                        raise WorkflowError(
                            "SOURCE_MEDICAL_EXCHANGE_MISSING: recover the original owned exchange."
                        )
        return row, body, actor

    def _current(self, c: Connection, actor: ActorRef) -> GameState:
        if not HandlerService(self.store)._member(c, int(actor.entity)):
            raise WorkflowError("Recover the original patient's campaign membership.")
        state = load_state(c, self.store.campaign_id)
        resolve(state, actor, profiles(c, self.store.campaign_id), require_current_profile=False)
        return state

    def _handler(self, c: Connection) -> tuple[int, str]:
        helper = HandlerService(self.store)
        owner = helper.current(c)[1].handler_id
        if (
            owner is None
            or owner != load_state(c, self.store.campaign_id).handler
            or not helper._member(c, owner)
        ):
            raise WorkflowError("Recover the actual current medical facilitator appointment.")
        setup = t.setup_revisions
        event = c.scalar(
            sa.select(setup.c.event_id)
            .join(t.events, t.events.c.id == setup.c.event_id)
            .where(
                setup.c.campaign_id == self.store.campaign_id,
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.kind == "campaign.handler_appointed",
            )
            .order_by(setup.c.revision.desc())
            .limit(1)
        )
        if event is None:
            raise WorkflowError("Recover the original medical facilitator appointment source.")
        return owner, str(event)

    def _view(self, c: Connection, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        self.game.authorize(c, viewer, game=False)
        row, body, actor = self._source(c, identity)
        own = actor.entity == str(viewer.user_id)
        if not own and body.get("reviewer") != viewer.user_id:
            raise WorkflowError("This care request belongs to its original participants.")
        stale = False
        try:
            state = self._current(c, actor)
        except (ValueError, WorkflowError):
            stale, state = True, load_state(c, self.store.campaign_id)
        stage = body.get("stage", "need_care")
        if body.get("resolution") == "original_character_career_ended":
            stage = "archived"
        reviewer_current = False
        if not own and stage == "awaiting_confirmation":
            try:
                reviewer_current = self._handler(c) == (viewer.user_id, body["appointment"])
            except WorkflowError:
                pass
        result: dict[str, Any] = dict(
            id=identity,
            revision=row["revision"],
            game_revision=state.revision,
            owner=own,
            actor=actor.model_dump(mode="json"),
            stage=stage,
            stale=stale,
            care=body.get("care"),
            evidence=body.get("evidence", ""),
            can_propose=own and not stale and stage in ("need_care", "awaiting_confirmation"),
            can_confirm=not stale
            and reviewer_current
            and row["state"] == "pending"
            and stage == "awaiting_confirmation",
            can_exchange=own
            and not stale
            and stage in ("choose_play", "standards_setup")
            and row["state"] == "pending",
            pending_exchange=body.get("pending_exchange") if own else None,
            can_setup_standards=own and not stale and stage == "standards_setup",
        )
        if own and stage in ("choose_play", "standards_setup") and not stale:
            try:
                result["choices"] = rules.choices(state, actor, load_registry())
            except WorkflowError:
                result["choices"] = None
        return result

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            return self._view(c, viewer, identity)

    def _save(
        self,
        c: Connection,
        row: dict[str, Any],
        event: str,
        body: dict[str, Any],
        *,
        resolved: bool = False,
    ) -> None:
        c.execute(
            t.m3["m3_required_work"]
            .insert()
            .values(
                **{
                    k: v
                    for k, v in row.items()
                    if k not in ("revision", "body_json", "event_id", "state")
                },
                revision=row["revision"] + 1,
                body_json=json.dumps(body, sort_keys=True),
                event_id=event,
                state="resolved" if resolved else "pending",
            )
        )

    def _idle(self, c: Connection) -> None:
        locks = t.m2["m2_locks"]
        if self.game.pending_actions(c) or c.scalar(
            sa.select(locks.c.channel_id)
            .where(
                locks.c.campaign_id == self.store.campaign_id,
                locks.c.state != "released",
            )
            .limit(1)
        ):
            raise WorkflowError("Finish actual Plays and restore chat before medical effects.")

    def _access(self, c: Connection, viewer: GuildViewer, identity: str) -> None:
        Access(self.store).authorize(c, viewer, "plays")
        _, body, _ = self._source(c, identity)
        action = self.game.action(c, body["source_action"])
        approval = self.store.policy.m3_approval
        if approval is None or action["data"]["defeat"]["registry"] != approval.registry_sha256:
            raise WorkflowError("M3_POLICY_CHANGED: recover the original Defeat approval.")

    def propose(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, care: Care
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self._access(c, viewer, identity)
            _, _, actor = self._source(c, identity)
            if actor.entity != str(viewer.user_id):
                raise WorkflowError("Only the original patient owns the care proposal.")

        def operation(c: Connection) -> dict[str, Any]:
            row, body, actor = self._source(c, identity)
            self._current(c, actor)
            if (
                row["revision"] != revision
                or row["state"] != "pending"
                or body.get("stage", "need_care") not in ("need_care", "awaiting_confirmation")
            ):
                raise WorkflowError("STALE_MEDICAL: reopen your actual current care request.")
            reviewer, appointment = self._handler(c)
            source = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.medical_care_proposed",
                work_id=identity,
                care_sha256=fingerprint(care),
            )
            self._save(
                c,
                row,
                source,
                body
                | dict(
                    care=care.model_dump(mode="json"),
                    reviewer=reviewer,
                    appointment=appointment,
                    stage="awaiting_confirmation",
                    evidence="",
                ),
            )
            return dict(id=identity, revision=revision + 1, stage="awaiting_confirmation")

        try:
            care = Care.model_validate_json(care.model_dump_json())
            return self.store._write(
                viewer,
                key,
                "m3.medical_care_proposed",
                dict(id=identity, revision=revision, care=care.model_dump(mode="json")),
                operation,
                authorize=access,
                auto_audit=False,
            )
        except ValidationError:
            raise WorkflowError("Describe valid actual medical care and waking.") from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def confirm(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        accept: bool,
        evidence: str,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self._access(c, viewer, identity)
            HandlerService(self.store).authorize(c, viewer)
            _, body, _ = self._source(c, identity)
            if (
                self._handler(c) != (viewer.user_id, body.get("appointment"))
                or body.get("reviewer") != viewer.user_id
            ):
                raise WorkflowError("Recover the care request's original facilitator appointment.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row, body, actor = self._source(c, identity)
            state = self._current(c, actor)
            if (
                type(accept) is not bool
                or not evidence.strip()
                or len(evidence) > 1200
                or row["revision"] != revision
                or state.revision != game_revision
                or row["state"] != "pending"
                or body.get("stage") != "awaiting_confirmation"
            ):
                raise WorkflowError(
                    "STALE_MEDICAL: review the actual care proposal and factual evidence."
                )
            care = Care.model_validate_json(json.dumps(body["care"]))
            source = str(uuid4())
            if accept:
                self._idle(c)
                state = rules.wake(state, actor, profiles(c, self.store.campaign_id), care, source)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.medical_wake_confirmed" if accept else "m3.medical_care_declined",
                state if accept else None,
                event_id=source,
                work_id=identity,
                care_sha256=fingerprint(care),
            )
            self._save(
                c,
                row,
                source,
                body
                | dict(
                    stage="choose_play" if accept else "need_care",
                    evidence=evidence.strip(),
                    immediate=accept,
                ),
            )
            return dict(
                id=identity, revision=revision + 1, stage="choose_play" if accept else "need_care"
            )

        try:
            return self.store._write(
                viewer,
                key,
                "m3.medical_care_confirmed",
                dict(
                    id=identity,
                    revision=revision,
                    game_revision=game_revision,
                    accept=accept,
                    evidence=evidence,
                ),
                operation,
                authorize=access,
                auto_audit=False,
            )
        except ValidationError:
            raise WorkflowError("The actual medical source needs recovery.") from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def exchange(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        selected: Exchange,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self._access(c, viewer, identity)
            _, _, actor = self._source(c, identity)
            if actor.entity != str(viewer.user_id):
                raise WorkflowError("The original affected Girl owns this Play exchange.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row, body, actor = self._source(c, identity)
            state = self._current(c, actor)
            if (
                row["revision"] != revision
                or state.revision != game_revision
                or row["state"] != "pending"
                or body.get("stage") not in ("choose_play", "standards_setup")
            ):
                raise WorkflowError(
                    "STALE_MEDICAL_EXCHANGE: review your actual current Girl Plays."
                )
            self._idle(c)
            source = str(uuid4())
            from girlframe.engine import m3_standards as standards
            from girlframe.services.m3_standards import StandardsService

            setup = StandardsService(self.store)
            if selected.acquired == standards.RULE and not standards.ready(
                state.sheets[actor.entity]
            ):
                available = rules.choices(state, actor, load_registry())
                if selected.removed not in {
                    x["id"] for x in available["removed"]
                } or selected.acquired not in {x["id"] for x in available["acquired"]}:
                    raise WorkflowError(
                        "Choose actual available Girl Plays for the pending exchange."
                    )
                compiled = setup.compiled(c, actor, identity)
                if compiled is None:
                    self.game.event(
                        c,
                        viewer.user_id,
                        key,
                        "m3.medical_standards_required",
                        event_id=source,
                        work_id=identity,
                        exchange_sha256=fingerprint(selected),
                    )
                    self._save(
                        c,
                        row,
                        source,
                        body
                        | dict(
                            stage="standards_setup",
                            immediate=True,
                            pending_exchange=selected.model_dump(mode="json"),
                        ),
                    )
                    return dict(id=identity, revision=revision + 1, stage="standards_setup")
                plan, grants = compiled
                state = standards.grant(state, plan, grants, profiles(c, self.store.campaign_id))
            state = rules.exchange(
                state, actor, profiles(c, self.store.campaign_id), selected, load_registry(), source
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.medical_play_exchanged",
                state,
                event_id=source,
                work_id=identity,
                exchange_sha256=fingerprint(selected),
            )
            setup.supersede(c, identity, source)
            self._save(
                c,
                row,
                source,
                body
                | dict(
                    stage="complete", immediate=False, exchange=selected.model_dump(mode="json")
                ),
                resolved=True,
            )
            return dict(id=identity, revision=revision + 1, stage="complete")

        try:
            selected = Exchange.model_validate_json(selected.model_dump_json())
            return self.store._write(
                viewer,
                key,
                "m3.medical_play_exchanged",
                dict(
                    id=identity,
                    revision=revision,
                    game_revision=game_revision,
                    exchange=selected.model_dump(mode="json"),
                ),
                operation,
                authorize=access,
                auto_audit=False,
            )
        except ValidationError:
            raise WorkflowError("Choose a valid original Girl Play exchange.") from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _tasks(
        self, c: Connection, viewer: GuildViewer, *, history: bool = False
    ) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        table = t.m3["m3_required_work"]
        rows = {
            x["id"]: dict(x)
            for x in c.execute(
                sa.select(table)
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.kind == KIND,
                )
                .order_by(table.c.revision)
            ).mappings()
        }
        result = []
        for row in rows.values():
            body = json.loads(row["body_json"])
            if row["owner_id"] != str(viewer.user_id) and body.get("reviewer") != viewer.user_id:
                continue
            if not history and row["state"] == "resolved":
                continue
            data = self._view(c, viewer, row["id"])
            result.append(
                dict(
                    id=row["id"],
                    revision=row["revision"],
                    stage=data["stage"],
                    state=row["state"],
                    stale=data["stale"],
                    label="Defeat medical recovery",
                    actionable=data["can_propose"] or data["can_confirm"] or data["can_exchange"],
                )
            )
        return result

    def tasks(self, viewer: GuildViewer, *, history: bool = False) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            return self._tasks(c, viewer, history=history)
