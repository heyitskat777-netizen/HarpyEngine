"""Private Handler rescue release, with actual source, medical and body confirmation."""

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_recovery as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actor_history import snapshot_profiles
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def _source(game: "GameService", c: Connection, state: GameState, identity: str) -> dict[str, Any]:
    candidates = []
    for fact in state.facts:
        if fact.get("kind") != "defeat_resolved":
            continue
        actor = ActorRef.model_validate_json(fact["actor"])
        if rules.task_id(fact["action"], actor) == identity:
            candidates.append((fact, actor))
    if len(candidates) != 1:
        raise WorkflowError("Recover this actual original Defeat rescue source")
    fact, actor = candidates[0]
    action = game.action(c, fact["action"])
    if (
        action["actor_id"] != actor.entity
        or action["data"].get("play") != "defeat"
        or action["data"].get("defeat", {}).get("actor") != actor.model_dump(mode="json")
    ):
        raise WorkflowError("Recover the original rescued person's actual Defeat action")
    receipts = t.m2["m2_receipts"]
    receipt = c.scalar(
        sa.select(receipts.c.body_json).where(
            receipts.c.campaign_id == game.store.campaign_id,
            receipts.c.action_id == action["id"],
        )
    )
    choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
    raw_answer = c.scalar(
        sa.select(responses.c.answer_json)
        .join(
            choices,
            sa.and_(
                choices.c.campaign_id == responses.c.campaign_id,
                choices.c.id == responses.c.choice_id,
            ),
        )
        .where(
            responses.c.campaign_id == game.store.campaign_id,
            responses.c.event_id == fact["source_event"],
            responses.c.actor_id == actor.entity,
            choices.c.action_id == action["id"],
            choices.c.kind == "defeat_select",
        )
    )
    born = _history(c, game, fact["source_event"])
    pose = next((x for x in born.placements if x.actor == actor), None)
    level = action["data"].get("result", {}).get("tier")
    answer = json.loads(raw_answer) if raw_answer else {}
    if (
        receipt is None
        or json.loads(receipt) != action["data"].get("receipt")
        or fact not in born.facts
        or pose is None
        or pose.source_event != fact["source_event"]
        or pose.custody is None
        or pose.custody.kind != "handler"
        or pose.custody != active_handler(born)
        or not (
            level == "high"
            or level == "mid"
            and "handler_rescue_swap_girl_play_on_waking" in answer.get("options", ())
        )
        or raw_answer is None
    ):
        raise WorkflowError(
            "Preserve the actual rolled rescue, owned answer and original custody snapshot"
        )
    return dict(
        id=identity,
        actor=actor,
        handler=pose.custody,
        action=action,
        rescue_event=fact["source_event"],
        original=pose,
        level=level,
    )


class HandlerRecoveryService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        Access(self.store).authorize(c, viewer, "plays", director_response=True)

    def _party(self, viewer: GuildViewer, source: dict[str, Any]) -> None:
        if viewer.user_id not in (int(source["actor"].entity), int(source["handler"].entity)):
            raise WorkflowError(
                "Only the actual rescued person and original Handler read this release"
            )

    def _proposal(self, c: Connection, source: dict[str, Any], value: rules.Proposal) -> None:
        row = c.execute(
            sa.select(t.events.c.kind, t.events.c.actor_id).where(
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.id == value.event,
            )
        ).first()
        if (
            row is None
            or tuple(row) != ("m3.handler_rescue_release_proposed", source["handler"].entity)
            or value.id != source["id"]
            or value.actor != source["actor"]
            or value.handler != source["handler"]
            or value.action != source["action"]["id"]
            or value.rescue_event != source["rescue_event"]
            or value.vessel != source["original"].vessel_id
            or value not in rules.proposals(_history(c, self.game, value.event), value.id)
        ):
            raise WorkflowError("Recover the exact original Handler's witnessed release proposal")

    def _context(self, c: Connection, state: GameState, source: dict[str, Any]) -> dict[str, Any]:
        actor, handler = source["actor"], source["handler"]
        bindings = snapshot_profiles(c, self.store.campaign_id, state)
        patient = resolve(
            state, actor, bindings, require_alive=False, require_current_profile=False
        )
        custodian = resolve(
            state, handler, bindings, require_alive=False, require_current_profile=False
        )
        pose = next((x for x in state.placements if x.actor == actor), None)
        if (
            active_handler(state) != handler
            or not patient.alive
            or not custodian.alive
            or pose is None
            or pose.vessel_id != source["original"].vessel_id
            or patient.vessel_id != pose.vessel_id
            or pose.custody != handler
            or patient.custody != "handler:" + handler.entity
            or patient.offstage_source
            or pose.mode != "outside_frame"
            or pose.occupied_frame_owner is not None
            or pose.incapacitated
            or pose.subsumed
            or not pose.vitals_active
            or state.sheets[actor.entity].medical_state != "fit"
            or custodian.custody not in (None, "free")
            or custodian.offstage_source
            or any(
                (x.active and actor in (x.traveler, x.supervisor)) or actor in x.offstage_refs
                for x in state.escort_journeys
            )
            or any(
                x.actor == actor and x.protection_release_event is None and x.stage == "prevented"
                for x in state.void_thresholds
            )
            or is_helpless(state, actor)
        ):
            raise WorkflowError(
                "Recover the same living fit body, original Handler and independent holds first"
            )
        if source["level"] == "mid":
            medical = MedicalService(self.store)
            matching = []
            for index, item in enumerate(source["action"]["data"].get("defeat_followups", ())):
                if item["kind"] == "medical_wake" and item["owner"] == actor.model_dump(
                    mode="json"
                ):
                    from uuid import NAMESPACE_URL, uuid5

                    work = str(
                        uuid5(
                            NAMESPACE_URL,
                            "girlframe:defeat:" + source["action"]["id"] + ":" + str(index),
                        )
                    )
                    row, body, original = medical._source(c, work)
                    matching.append(
                        row["state"] == "resolved"
                        and body.get("stage") == "complete"
                        and original == actor
                    )
            if matching != [True]:
                raise WorkflowError(
                    "Complete the actual original medical waking and required Play exchange first"
                )
        if custodian.cell is not None and (
            state.world is None or not state.world.board.contains(custodian.cell)
        ):
            raise WorkflowError("Recover the original Handler's actual on-map physical position")
        return dict(pose=pose, cell=custodian.cell, custodian=custodian)

    def _view(
        self, c: Connection, viewer: GuildViewer, state: GameState, identity: str
    ) -> dict[str, Any]:
        source = _source(self.game, c, state, identity)
        self._party(viewer, source)
        released = rules.released(state, identity)
        values = rules.proposals(state, identity)
        proposal = values[-1] if values else None
        if proposal is not None:
            self._proposal(c, source, proposal)
        if released is not None:
            row = c.execute(
                sa.select(t.events.c.kind, t.events.c.actor_id).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == released.event,
                )
            ).first()
            if (
                proposal is None
                or released.id != identity
                or released.actor != source["actor"]
                or released.handler != source["handler"]
                or released.proposal != proposal.event
                or row is None
                or tuple(row) != ("m3.handler_rescue_released", source["actor"].entity)
                or rules.released(_history(c, self.game, released.event), identity) != released
            ):
                raise WorkflowError("Recover the actual original rescued body's release event")
        blocked, cell = None, released.cell if released else None
        if released is None:
            try:
                cell = self._context(c, state, source)["cell"]
            except (ValueError, WorkflowError) as exc:
                blocked = str(exc)
        handler = viewer.user_id == int(source["handler"].entity)
        return dict(
            id=identity,
            revision=state.revision,
            source_action=source["action"]["id"],
            actor=source["actor"].model_dump(mode="json"),
            handler=source["handler"].model_dump(mode="json"),
            vessel=source["original"].vessel_id,
            phase="released"
            if released
            else "blocked"
            if blocked
            else "awaiting_patient"
            if proposal
            else "awaiting_handler",
            pending=released is None,
            label="Actual Handler rescue discharge",
            cell=cell,
            may_record_presence=handler and released is None and not blocked and cell is None,
            may_propose=handler and released is None and not blocked and cell is not None,
            may_confirm=not handler and released is None and not blocked and proposal is not None,
            proposal=proposal.model_dump(mode="json") if proposal else None,
            release=released.model_dump(mode="json") if released else None,
            blocked=blocked,
            board=state.world.board.model_dump(mode="json") if state.world else None,
        )

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            return self._view(c, viewer, load_state(c, self.store.campaign_id), identity)

    def _tasks(
        self, c: Connection, viewer: GuildViewer, *, history: bool = False
    ) -> list[dict[str, Any]]:
        self._access(c, viewer)
        state = load_state(c, self.store.campaign_id)
        result = []
        for fact in state.facts:
            if fact.get("kind") != "defeat_resolved":
                continue
            actor = ActorRef.model_validate_json(fact["actor"])
            identity = rules.task_id(fact["action"], actor)
            try:
                shown = self._view(c, viewer, state, identity)
            except (ValueError, WorkflowError):
                continue
            if shown["pending"] or history:
                result.append(
                    dict(
                        id=identity,
                        revision=state.revision,
                        pending=shown["pending"],
                        phase=shown["phase"],
                        label=shown["label"],
                        actionable=any(
                            shown.get(key, False)
                            for key in ("may_record_presence", "may_propose", "may_confirm")
                        ),
                    )
                )
        return result

    def tasks(self, viewer: GuildViewer, *, history: bool = False) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            return self._tasks(c, viewer, history=history)

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        kind: str,
        payload: dict[str, Any],
        operation: Callable[
            [Connection, GameState, dict[str, Any], dict[str, Any], str], GameState
        ],
    ) -> dict[str, Any]:
        def run(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            if state.revision != expected:
                raise WorkflowError("STALE_HANDLER_RECOVERY: reopen the original release")
            source = _source(self.game, c, state, identity)
            self._party(viewer, source)
            if rules.released(state, identity) is not None:
                raise WorkflowError("The original rescue release has already completed")
            MedicalService(self.store)._idle(c)
            context = self._context(c, state, source)
            event = str(uuid4())
            updated = operation(c, state, source, context, event)
            self.game.event(c, viewer.user_id, key, kind, updated, event_id=event, work_id=identity)
            return dict(id=identity, revision=updated.revision, event=event)

        try:
            return self.store._write(
                viewer,
                key,
                kind,
                dict(id=identity, expected=expected, **payload),
                run,
                auto_audit=False,
                authorize=lambda c: self._access(c, viewer),
            )
        except ValueError as exc:
            raise WorkflowError(str(exc)) from None

    def record_initial_presence(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        cell: tuple[int, int],
        account: str,
    ) -> dict[str, Any]:
        def operation(
            c: Connection,
            state: GameState,
            source: dict[str, Any],
            context: dict[str, Any],
            event: str,
        ) -> GameState:
            HandlerService(self.store).authorize(c, viewer)
            if (
                viewer.user_id != int(source["handler"].entity)
                or context["cell"] is not None
                or context["custodian"].occupied_frame_instance is not None
                or len(cell) != 2
                or any(type(x) is not int for x in cell)
                or state.world is None
                or not state.world.board.contains(cell)
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "Only the original Handler records witnessed "
                    "previously unknown initial presence"
                )
            state.facts.append(
                dict(
                    kind="recorded_handler_recovery_position",
                    actor=source["handler"].model_dump_json(),
                    cell=json.dumps(cell),
                    event=event,
                    source_action=source["action"]["id"],
                    work=identity,
                    account=account,
                )
            )
            return state

        return self._write(
            viewer,
            key,
            identity,
            expected,
            "m3.handler_rescue_presence_recorded",
            dict(cell=list(cell), account=account),
            operation,
        )

    def propose(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, account: str
    ) -> dict[str, Any]:
        def operation(
            c: Connection,
            state: GameState,
            source: dict[str, Any],
            context: dict[str, Any],
            event: str,
        ) -> GameState:
            HandlerService(self.store).authorize(c, viewer)
            if viewer.user_id != int(source["handler"].entity) or context["cell"] is None:
                raise WorkflowError(
                    "The original Handler proposes release at their actual known current position"
                )
            if not account.strip() or len(account) > 1200:
                raise WorkflowError("Record witnessed release facts, not an unperformed transport")
            value = rules.Proposal(
                id=identity,
                action=source["action"]["id"],
                rescue_event=source["rescue_event"],
                actor=source["actor"],
                handler=source["handler"],
                vessel=context["pose"].vessel_id,
                origin=context["pose"],
                cell=context["cell"],
                account=account,
                event=event,
            )
            rules.put(state, value)
            return state

        return self._write(
            viewer,
            key,
            identity,
            expected,
            "m3.handler_rescue_release_proposed",
            dict(account=account),
            operation,
        )

    def confirm(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        proposal_event: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(
            c: Connection,
            state: GameState,
            source: dict[str, Any],
            context: dict[str, Any],
            event: str,
        ) -> GameState:
            values = rules.proposals(state, identity)
            value = values[-1] if values else None
            if value is not None:
                self._proposal(c, source, value)
            if (
                viewer.user_id != int(source["actor"].entity)
                or value is None
                or value.event != proposal_event
                or value.cell != context["cell"]
                or value.origin != context["pose"]
                or not account.strip()
                or len(account) > 1200
                or value not in rules.proposals(_history(c, self.game, value.event), identity)
            ):
                raise WorkflowError(
                    "Confirm the exact current original body, witnessed source "
                    "and actual release position"
                )
            return rules.discharge(state, value, event, account)

        return self._write(
            viewer,
            key,
            identity,
            expected,
            "m3.handler_rescue_released",
            dict(proposal_event=proposal_event, account=account),
            operation,
        )
