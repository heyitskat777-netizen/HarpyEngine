"""Bind the next mission to the real High Budget demand and prove its outcome."""

import json

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_budget_conversion as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_handler_conversion import records
from girlframe.engine.m3_missions import Mission
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError


def pending(state: GameState) -> tuple[rules.CaptureOrder, ...]:
    return tuple(x for x in rules.orders(state) if not x.dispatched)


def targets(state: GameState) -> tuple[tuple[str, str], ...]:
    handler = active_handler(state)
    if handler is None:
        return ()
    known = {
        role.actor.entity
        for scene in state.scene_casts
        if scene.open and any(x.actor == handler for x in scene.roles)
        for role in scene.roles
        if role.actor.kind == "external_pilot"
    }
    return tuple(
        (x.id, x.name)
        for x in state.harpy_states
        if x.alive and x.custody == "free" and (x.revealed or x.id in known)
    )


def _proof(c: Connection, game: GameService, value: rules.CaptureOrder) -> None:
    history = t.m2["m2_state_history"]
    birth = c.execute(
        sa.select(history.c.body_json, t.events.c.payload_json)
        .join(
            t.events,
            (t.events.c.campaign_id == history.c.campaign_id)
            & (t.events.c.id == history.c.event_id),
        )
        .where(
            history.c.campaign_id == game.store.campaign_id,
            history.c.event_id == value.source_event,
            t.events.c.kind == "m3.strain_effect_applied",
            t.events.c.actor_id == value.handler.entity,
        )
    ).first()
    original = value.model_copy(
        update=dict(mission=None, target=None, dispatched=None, settled=None, conversion=None)
    )
    if birth is None or original not in rules.orders(
        GameState.model_validate_json(birth.body_json)
    ):
        raise WorkflowError("Recover the original High Budget capture and conversion demand")
    audit = json.loads(birth.payload_json)
    if audit.get("rule_id") != rules.RULE or audit.get("work_id") != value.id:
        raise WorkflowError("Recover the actual source of the High Budget conversion mission")


def check_dispatch(c: Connection, game: GameService, state: GameState, mission: Mission) -> None:
    due = pending(state)
    if not due and mission.capture_target is None:
        return
    if (
        not due
        or mission.capture_target is None
        or mission.capture_target.entity not in dict(targets(state))
    ):
        raise WorkflowError("The next mission must target an actual known Harpy for conversion")
    for value in due:
        _proof(c, game, value)
        if not same_handler_body(state, value.handler):
            raise WorkflowError("Review the demand after the original Handler's departure")


def bind(state: GameState, mission: Mission, dispatch: str) -> None:
    for value in pending(state):
        rules.put(
            state,
            value.model_copy(
                update=dict(mission=mission.id, target=mission.capture_target, dispatched=dispatch)
            ),
        )


def outcome(c: Connection, game: GameService, state: GameState, mission: Mission) -> str:
    from girlframe.services.m3_handler_conversion import prove_repossession

    due = tuple(x for x in rules.orders(state) if x.mission == mission.id and not x.settled)
    if not due or mission.capture_target is None:
        raise WorkflowError("Recover this conversion mission's original dispatch and target")

    def order(event: str, kind: str, *, mission_id: str | None = None) -> int:
        row = c.execute(
            sa.select(t.events.c.seq, t.events.c.payload_json).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == event,
                t.events.c.kind == kind,
            )
        ).first()
        if row is None or (
            mission_id and json.loads(row.payload_json).get("mission_id") != mission_id
        ):
            raise WorkflowError("Recover the original conversion mission and its event sequence")
        return int(row.seq)

    dispatched = due[0].dispatched
    if not dispatched or any(
        x.dispatched != dispatched or x.target != mission.capture_target for x in due
    ):
        raise WorkflowError("Recover the actual original dispatch and capture target")
    for value in due:
        _proof(c, game, value)
    started = order(dispatched, "m3.mission_started", mission_id=mission.id)
    for candidate in records(state):
        if candidate.actor != mission.capture_target or candidate.phase != "complete":
            continue
        actual = prove_repossession(game, c, state, candidate.id)
        if actual.handler != due[0].handler or actual.completion_event is None:
            continue
        capture = next((x for x in state.harpy_defeats if x.id == actual.capture_effect), None)
        captor = capture.captor if capture else None
        if captor is None or (
            captor != actual.handler
            and (
                captor.kind != "pilot"
                or mission.character_ids.get(captor.entity) != captor.incarnation
            )
        ):
            continue
        captured = c.scalar(
            sa.select(t.events.c.seq).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == actual.capture_event,
            )
        )
        completed = order(actual.completion_event, "m3.handler_conversion_completed")
        if captured is not None and started < captured < completed:
            return actual.completion_event
    raise WorkflowError("Complete the original target's actual in-mission capture and conversion")


def settle(
    c: Connection, game: GameService, state: GameState, mission: Mission, success: bool, event: str
) -> None:
    if mission.capture_target is None:
        return
    due = tuple(x for x in rules.orders(state) if x.mission == mission.id and not x.settled)
    if not due or any(not x.dispatched or x.target != mission.capture_target for x in due):
        raise WorkflowError("Recover the original required mission binding before settlement")
    conversion = outcome(c, game, state, mission) if success else None
    for value in due:
        _proof(c, game, value)
        rules.put(state, value.model_copy(update=dict(settled=event, conversion=conversion)))
