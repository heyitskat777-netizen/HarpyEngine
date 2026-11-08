"""Real Low Rebellion prisoner escape, actual movement and source-backed resolution."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_prisoner_escape as rules
from girlframe.engine import m3_strain as strain_rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import is_helpless
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _cast, _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_void import _append
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _get[T: Model](state: GameState, model: type[T], identity: str) -> T:
    try:
        return rules.get(state, model, identity)
    except ValueError as error:
        raise WorkflowError(str(error)) from None


def _event(game: GameService, c: Connection, identity: str) -> Any:
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == identity,
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise WorkflowError("Recover the original canonical prisoner event")
    return row


def _before(game: GameService, c: Connection, identity: str) -> GameState:
    event = _event(game, c, identity)
    history = t.m2["m2_state_history"]
    raw = c.scalar(
        sa.select(history.c.body_json)
        .join(t.events, history.c.event_id == t.events.c.id)
        .where(
            history.c.campaign_id == game.store.campaign_id,
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.seq < event["seq"],
        )
        .order_by(t.events.c.seq.desc())
        .limit(1)
    )
    if raw is None:
        raise WorkflowError("Recover the actual before-state of this source")
    return GameState.model_validate_json(raw)


def _work(
    game: GameService, c: Connection, identity: str, *, first: bool = False
) -> dict[str, Any]:
    table = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(table)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == identity)
            .order_by(table.c.revision if first else table.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None:
        raise WorkflowError("Recover this original pending Strain effect")
    return dict(row)


def _strain_source(game: GameService, c: Connection, identity: str) -> dict[str, Any]:
    row = _work(game, c, identity, first=True)
    body = json.loads(row["body_json"])
    event = _event(game, c, row["event_id"])
    payload = json.loads(event["payload_json"])
    saved = _history(c, game, row["event_id"])
    chosen = (
        next((x for x in saved.strain.events if x.id == body.get("source_work")), None)
        if saved.strain
        else None
    )
    if (
        row["kind"] != "strain_event"
        or body.get("rule_id") != rules.RULE
        or event["kind"] != "m3.strain_option_saved"
        or payload.get("rule_id") != rules.RULE
        or payload.get("work_id") != body.get("source_work")
        or chosen is None
        or chosen.rule_id != rules.RULE
        or chosen.period_id != row["off_duty_id"]
    ):
        raise WorkflowError("Use the actual selected Low Rebellion die4 column2 source")
    return row


def _npc(state: GameState, actor: ActorRef) -> Npc:
    npc = next((x for x in state.world.npcs if x.id == actor.entity), None) if state.world else None
    if actor.kind != "npc" or npc is None or npc.source_kind is not None:
        raise WorkflowError("Use this actual ordinary original NPC, not a proxy Pilot or Wraith")
    return npc


def _custody(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> Npc:
    npc = _npc(state, actor)
    if (
        not npc.alive
        or "prisoner" not in npc.jobs
        or not npc.custody_event
        or npc.captive_of is not None
        or is_helpless(state, actor)
        or rules.active(state, actor)
        or state.world is None
        or not any(
            x.cell == npc.cell
            and x.kind == "base"
            and x.allegiance == "foundation"
            and x.condition != "destroyed"
            for x in state.world.locations
        )
    ):
        raise WorkflowError("Use actual current introductory Foundation prisoner custody")
    event = _event(game, c, npc.custody_event)
    old = _npc(_history(c, game, npc.custody_event), actor)
    actual = resolve(
        state, actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if (
        event["kind"] != "m3.npc_introduced"
        or json.loads(event["payload_json"]).get("entity_id") != npc.id
        or old.custody_event != npc.custody_event
        or "prisoner" not in old.jobs
        or not old.alive
        or actual.custody not in (None, "free")
    ):
        raise WorkflowError("Prove genuine server-introduced prisoner custody, not a job label")
    return npc


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Attempt:
    value = next(
        (x for x in rules.records(state, rules.Attempt) if identity in (x.id, x.work)), None
    )
    if value is None:
        raise WorkflowError("Recover the original actual prisoner attempt")
    row = _strain_source(game, c, value.work)
    event = _event(game, c, value.event)
    born = _history(c, game, value.event)
    prior = _before(game, c, value.event)
    if (
        value.id != rules.identity(game.store.campaign_id, value.work)
        or value.source_event != row["event_id"]
        or value.period != row["off_duty_id"]
        or value.controller != int(row["owner_id"])
        or event["kind"] != "m3.prisoner_escape_started"
        or event["actor_id"] != str(value.controller)
        or _get(born, rules.Attempt, value.id) != value
        or _npc(prior, value.prisoner) != value.before
        or _npc(born, value.prisoner) != value.before.model_copy(update=dict(custody_event=None))
        or _custody(game, c, prior, value.prisoner) != value.before
        or active_handler(prior) != value.handler
        or value.handler.entity != str(value.controller)
    ):
        raise WorkflowError("Preserve the original source/custody release and actual Handler")
    outcome = rules.resolution(state, value)
    if outcome is not None:
        saved = _history(c, game, outcome.event)
        if (
            _get(saved, rules.Resolution, outcome.id) != outcome
            or _event(game, c, outcome.event)["kind"] != "m3.prisoner_escape_resolved"
            or outcome.id != rules.identity("resolution", value.id)
            or saved.strain is None
            or saved.strain.levels["rebellion"] != outcome.after
        ):
            raise WorkflowError("Only the actual immutable finding closes the source")
    return value


def stage_movement(
    game: GameService,
    c: Connection,
    before: GameState,
    after: GameState,
    context: dict[str, Any],
    event: str,
) -> None:
    if not rules.active(before):
        return
    actor = ActorRef.model_validate_json(json.dumps(context["actor"]))
    sources = rules.active(before, actor)
    if not sources:
        return
    old, new = _npc(before, actor), _npc(after, actor)
    if (
        old.custody_event
        or new.custody_event
        or old.captive_of
        or new.captive_of
        or not old.alive
        or not new.alive
        or context["controller"] != old.controller
        or tuple(context["origin"]) != old.cell
        or tuple(context["destination"]) != new.cell
        or context["frame"]
        or old.cell == new.cell
        or new != old.model_copy(update=dict(cell=new.cell))
    ):
        raise WorkflowError("Only this actual controlled free NPC's real movement is evidence")
    for candidate in sources:
        source = prove(game, c, before, candidate.id)
        rules.put(
            after,
            rules.MovementEvidence(
                id=rules.identity("movement", source.id, event),
                attempt=source.id,
                controller=context["controller"],
                context_json=json.dumps(context, sort_keys=True),
                event=event,
            ),
        )


def prove_movement(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.MovementEvidence:
    value = _get(state, rules.MovementEvidence, identity)
    source = prove(game, c, state, value.attempt)
    event = _event(game, c, value.event)
    context = json.loads(value.context_json)
    before, after = _before(game, c, value.event), _history(c, game, value.event)
    old, new = _npc(before, source.prisoner), _npc(after, source.prisoner)
    if (
        value.id != rules.identity("movement", source.id, value.event)
        or _get(after, rules.MovementEvidence, identity) != value
        or event["kind"] != "m3.physical_moved"
        or event["actor_id"] != str(value.controller)
        or context["actor"] != source.prisoner.model_dump(mode="json")
        or context["controller"] != value.controller
        or old.controller != value.controller
        or tuple(context["origin"]) != old.cell
        or tuple(context["destination"]) != new.cell
        or new != old.model_copy(update=dict(cell=new.cell))
        or old.cell == new.cell
        or old.custody_event is not None
        or new.custody_event is not None
    ):
        raise WorkflowError("Recover the canonical original NPC's true controlled escape movement")
    return value


def _grip(
    game: GameService,
    c: Connection,
    state: GameState,
    source: rules.Attempt,
    action_id: str,
    grip_id: str,
) -> tuple[dict[str, Any], ActorRef]:
    action = game.action(c, action_id)
    meta = action["data"].get("enforcement", {})
    grip = next((x for x in state.enforcer_grasps if x.id == grip_id), None)
    if not meta or grip is None:
        raise WorkflowError("Use an actual completed Enforcement Initiative and its real NPC grip")
    actor = ActorRef.model_validate_json(json.dumps(meta["actor"]))
    target = ActorRef.model_validate_json(json.dumps(meta["target"]))
    roll_event, total = _roll_source(game, c, action)
    born = _history(c, game, grip.source_event)
    original = next((x for x in born.enforcer_grasps if x.id == grip.id), None)
    if (
        action["data"].get("prepared", {}).get("play") != "enforcement_initiative"
        or action["state"] != "complete"
        or game.pending(c, action_id)
        or total < 8
        or actor.kind != "pilot"
        or int(actor.entity) not in born.order
        or target != source.prisoner
        or grip.target != target
        or grip.actor != actor
        or not grip.held
        or grip.action != action_id
        or meta.get("grasp") != grip_id
        or original is None
        or not original.held
        or original.model_copy(
            update=dict(
                held=grip.held,
                release_event=grip.release_event,
                release_account=grip.release_account,
            )
        )
        != grip
        or _event(game, c, roll_event)["seq"] <= _event(game, c, source.event)["seq"]
        or action["scene_id"] != source.cast.id
    ):
        raise WorkflowError(
            "Only the actual later Girl performance and still-active original hold "
            "deal with this attempt"
        )
    _npc(state, target)
    if not _npc(state, target).alive or not is_helpless(state, target):
        raise WorkflowError(
            "Preserve the actual still-held living original NPC, not inferred capture"
        )
    return action, actor


def _text(value: str) -> None:
    if not value.strip() or len(value) > 1200:
        raise WorkflowError("Provide the actual original source account within its limit")


def _free(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> bool:
    actual = resolve(
        state,
        actor,
        profiles(c, game.store.campaign_id),
        require_alive=False,
        require_current_profile=False,
    )
    npc = _npc(state, actor)
    return bool(
        npc.alive
        and npc.custody_event is None
        and actual.cell is not None
        and actual.custody in (None, "free")
        and not is_helpless(state, actor)
    )


class PrisonerEscapeService:
    def __init__(self, strain: StrainService):
        self.strain, self.game, self.store = strain, strain.game, strain.store

    def _authorize(self, c: Connection, viewer: GuildViewer) -> None:
        gate = Access(self.store)
        gate.authorize(c, viewer, "world", director_response=True)
        gate.authorize(c, viewer, "strain", director_response=True)
        assert gate.registry is not None
        gate.registry.require_available(rules.RULE)

    def _handler(
        self, c: Connection, state: GameState, viewer: GuildViewer, source: rules.Attempt
    ) -> None:
        self.strain._authorize(c, viewer)
        if (
            viewer.user_id != source.controller
            or active_handler(state) != source.handler
            or HandlerCreationService(self.store)._appointment_source(c, viewer.user_id)
            != source.appointment
        ):
            raise WorkflowError("Only the original actual Handler adjudicates this source")

    def start(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        work_revision: int,
        game_revision: int,
        channel: int,
        prisoner: ActorRef,
        account: str,
    ) -> dict[str, Any]:
        _text(account)

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            self.strain._authorize(c, viewer)
            row = _work(self.game, c, identity)
            self.strain._check(c, viewer, row, work_revision)
            original = _strain_source(self.game, c, identity)
            state = self.strain._state(c, game_revision)
            PhysicalService(self.store)._idle(c)
            if any(x.work == identity for x in rules.records(state, rules.Attempt)):
                raise WorkflowError("This actual selected event already has its prisoner attempt")
            npc = _custody(self.game, c, state, prisoner)
            cast = _cast(self.game, c, state, channel)
            if not any(
                role.actor == prisoner and role.controller == npc.controller for role in cast.roles
            ):
                raise WorkflowError(
                    "Join the actual original prisoner role, not a controller proxy"
                )
            handler = active_handler(state)
            if handler is None or state.world is None:
                raise WorkflowError("Recover the actual source Handler/world")
            event = str(uuid4())
            source = rules.Attempt(
                id=rules.identity(self.store.campaign_id, identity),
                work=identity,
                source_event=original["event_id"],
                period=row["off_duty_id"],
                handler=handler,
                controller=viewer.user_id,
                appointment=HandlerCreationService(self.store)._appointment_source(
                    c, viewer.user_id
                ),
                prisoner=prisoner,
                before=npc,
                cast=cast,
                account=account,
                event=event,
            )
            rules.put(state, source)
            state.world = state.world.model_copy(
                update=dict(
                    npcs=tuple(
                        x.model_copy(update=dict(custody_event=None)) if x.id == npc.id else x
                        for x in state.world.npcs
                    )
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.prisoner_escape_started",
                state,
                event_id=event,
                attempt=source.id,
                work_id=identity,
            )
            _append(c, row, event, json.loads(row["body_json"]) | dict(attempt=source.id))
            return dict(id=source.id, work=identity, revision=state.revision, moved=False)

        return self.store._write(
            viewer,
            key,
            "m3.prisoner_escape_started",
            dict(
                work=identity,
                work_revision=work_revision,
                game_revision=game_revision,
                channel=channel,
                prisoner=prisoner.model_dump(mode="json"),
                account=account,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: self._authorize(c, viewer),
        )

    def _resolve(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        kind: str,
        account: str,
        *,
        evidence: str | None = None,
        action_id: str | None = None,
        grip_id: str | None = None,
    ) -> dict[str, Any]:
        _text(account)

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = self.strain._state(c, revision)
            PhysicalService(self.store)._idle(c)
            source = prove(self.game, c, state, identity)
            if rules.resolution(state, source) is not None or state.strain is None:
                raise WorkflowError("This actual prisoner attempt already has its real finding")
            row = _work(self.game, c, source.work)
            if row["state"] != "pending":
                raise WorkflowError("Preserve the actual still-pending Strain source")
            if kind == "dealt":
                _, actor = _grip(self.game, c, state, source, action_id or "", grip_id or "")
                actual = resolve(
                    state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
                )
                if actual.controller != viewer.user_id:
                    raise WorkflowError("The actual Girl performer records her real completed hold")
            else:
                self._handler(c, state, viewer, source)
                movement = prove_movement(self.game, c, state, evidence or "")
                npc = _npc(state, source.prisoner)
                context = json.loads(movement.context_json)
                actual = resolve(
                    state,
                    source.prisoner,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
                if (
                    movement.attempt != source.id
                    or not npc.alive
                    or npc.custody_event
                    or npc.captive_of
                    or npc.cell != tuple(context["destination"])
                    or actual.custody not in (None, "free")
                    or is_helpless(state, source.prisoner)
                    or any(x.held and x.target == source.prisoner for x in state.enforcer_grasps)
                    or state.world is None
                    or any(
                        x.cell == npc.cell
                        and x.kind == "base"
                        and x.allegiance == "foundation"
                        and x.condition != "destroyed"
                        for x in state.world.locations
                    )
                ):
                    raise WorkflowError(
                        "Failure needs actual ended free escape, not a pending or captured prisoner"
                    )
                actor = source.handler
            event = str(uuid4())
            previous = state.strain.levels["rebellion"]
            if kind == "failed":
                state.strain = strain_rules.copy(
                    state.strain, levels=state.strain.levels | {"rebellion": "high"}
                )
            outcome = rules.Resolution(
                id=rules.identity("resolution", source.id),
                attempt=source.id,
                kind="failed" if kind == "failed" else "dealt",
                actor=actor,
                controller=viewer.user_id,
                account=account,
                event=event,
                evidence=evidence,
                action=action_id,
                grip=grip_id,
                before=previous,
                after=state.strain.levels["rebellion"],
            )
            rules.put(state, outcome)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.prisoner_escape_resolved",
                state,
                event_id=event,
                attempt=source.id,
                resolution=outcome.id,
            )
            _append(
                c,
                row,
                event,
                json.loads(row["body_json"]) | dict(resolution=outcome.id),
                resolved=True,
            )
            return dict(
                id=source.id, revision=state.revision, result=outcome.kind, rebellion=outcome.after
            )

        return self.store._write(
            viewer,
            key,
            "m3.prisoner_escape_resolved",
            dict(
                id=identity,
                revision=revision,
                kind=kind,
                account=account,
                evidence=evidence,
                action=action_id,
                grip=grip_id,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: self._authorize(c, viewer),
        )

    def record_dealt(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        action_id: str,
        grip_id: str,
        account: str,
    ) -> dict[str, Any]:
        return self._resolve(
            viewer, key, identity, revision, "dealt", account, action_id=action_id, grip_id=grip_id
        )

    def resolve_failure(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        evidence_id: str,
        account: str,
    ) -> dict[str, Any]:
        return self._resolve(
            viewer, key, identity, revision, "failed", account, evidence=evidence_id
        )

    def _audience(self, state: GameState, source: rules.Attempt) -> set[int]:
        npc = _npc(state, source.prisoner)
        return {
            source.controller,
            source.before.controller,
            npc.controller,
            *(role.controller for role in source.cast.roles),
        }

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        for source in rules.records(state, rules.Attempt):
            if viewer.user_id not in self._audience(state, source):
                continue
            outcome = rules.resolution(state, source)
            npc = _npc(state, source.prisoner)
            movable = (
                outcome is None
                and viewer.user_id == npc.controller
                and _free(self.game, c, state, source.prisoner)
            )
            handler_action = (
                viewer.user_id == source.controller
                and _free(self.game, c, state, source.prisoner)
                and any(
                    x.attempt == source.id for x in rules.records(state, rules.MovementEvidence)
                )
            )
            girl_action = any(
                x.held and x.target == source.prisoner and x.actor.entity == str(viewer.user_id)
                for x in state.enforcer_grasps
            )
            result.append(
                dict(
                    id=source.work,
                    revision=state.revision,
                    label="Actual prisoner escape",
                    phase="resolved" if outcome else "pending",
                    pending=outcome is None and bool(movable or handler_action or girl_action),
                )
            )
        return result

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            source = next(
                (x for x in rules.records(state, rules.Attempt) if identity in (x.id, x.work)), None
            )
            if source is None:
                self.strain._authorize(c, viewer)
                row = _work(self.game, c, identity)
                _strain_source(self.game, c, identity)
                candidates = []
                if state.world and row["state"] == "pending":
                    for npc in state.world.npcs:
                        actor = ActorRef(kind="npc", entity=npc.id)
                        try:
                            _custody(self.game, c, state, actor)
                        except (ValueError, WorkflowError):
                            continue
                        candidates.append(
                            dict(
                                id=actor.token, label=npc.name, actor=actor.model_dump(mode="json")
                            )
                        )
                return dict(
                    id=identity,
                    type="start",
                    revision=state.revision,
                    work_revision=row["revision"],
                    state=row["state"],
                    candidates=candidates,
                )
            if viewer.user_id not in self._audience(state, source):
                raise WorkflowError(
                    "Only actual source participants read this private original attempt"
                )
            source = prove(self.game, c, state, source.id)
            outcome = rules.resolution(state, source)
            npc = _npc(state, source.prisoner)
            movements = [
                dict(
                    id=x.id,
                    label="Actual movement " + str(json.loads(x.context_json)["destination"]),
                )
                for x in rules.records(state, rules.MovementEvidence)
                if x.attempt == source.id
            ]
            grips = []
            if outcome is None:
                for grip in state.enforcer_grasps:
                    if grip.target != source.prisoner or not grip.held:
                        continue
                    try:
                        _, actor = _grip(self.game, c, state, source, grip.action, grip.id)
                        if (
                            resolve(
                                state,
                                actor,
                                profiles(c, self.store.campaign_id),
                                require_current_profile=False,
                            ).controller
                            != viewer.user_id
                        ):
                            continue
                    except (ValueError, WorkflowError):
                        continue
                    grips.append(
                        dict(
                            id=grip.id,
                            action=grip.action,
                            label="My actual completed Initiative hold",
                        )
                    )
            return dict(
                id=source.id,
                work=source.work,
                type="attempt",
                revision=state.revision,
                prisoner=npc.name,
                actor=source.prisoner.model_dump(mode="json"),
                account=source.account,
                state=outcome.kind if outcome else "attempt in progress",
                movements=movements,
                grips=grips,
                outcome_account=outcome.account if outcome else None,
                can_move=outcome is None
                and npc.controller == viewer.user_id
                and _free(self.game, c, state, source.prisoner),
                can_fail=outcome is None
                and source.controller == viewer.user_id
                and _free(self.game, c, state, source.prisoner),
            )
