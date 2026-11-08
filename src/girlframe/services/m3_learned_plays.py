"""Finite actual learned-Play admission and one-roll consumption; source effects stay explicit."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_girl_runtime_state import GirlRuntime, has_rule
from girlframe.engine.m3_learned_play_state import LearnedPlayUse
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError

SUPPORTED = {
    "girl.alpha.brutalize": ("brutalize", "ALPHA"),
    "girl.stim-blissed.dose-up": ("dose_up", "STIM-BLISSED"),
    "girl.oldgen.old-dog-new-pups": ("old_dog_new_pups", "OLDGEN"),
    "girl.newgirl.easy-target": ("easy_target", "NEWGIRL"),
}


def _replace(state: GameState, value: LearnedPlayUse) -> None:
    sheet = state.sheets[value.actor.entity]
    runtime = sheet.girl_runtime or GirlRuntime()
    sheet.girl_runtime = runtime.model_copy(
        update={
            "learned_plays": tuple(x for x in runtime.learned_plays if x.id != value.id) + (value,)
        }
    )
    sheet.revision += 1


def grant(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    teacher: ActorRef,
    session: str,
    rule_id: str,
    event: str,
) -> str:
    if rule_id not in SUPPORTED:
        raise WorkflowError(
            "UNSUPPORTED_LEARNED_PLAY: this real counterpart Play needs its consumer"
        )
    _, book = SUPPORTED[rule_id]
    if (
        actor.kind != "pilot"
        or teacher.kind != "pilot"
        or actor == teacher
        or not session
        or not event
        or actor != current_ref(state, int(actor.entity))
        or teacher != current_ref(state, int(teacher.entity))
        or not has_rule(state.sheets[teacher.entity], rule_id, book)
    ):
        raise WorkflowError("Preserve the actual original learner, teacher and chosen source Play")
    value = LearnedPlayUse(
        id=str(uuid4()), actor=actor, teacher=teacher, session=session, rule_id=rule_id, event=event
    )
    _replace(state, value)
    return value.id


def _prove(
    game: GameService,
    c: Connection,
    state: GameState,
    value: LearnedPlayUse,
) -> None:
    from girlframe.services.m3_vatgrown_plays import prove_learned_play

    source = prove_learned_play(game, c, state, value.id)
    if any(
        getattr(source, name) != getattr(value, name)
        for name in ("id", "actor", "teacher", "session", "rule_id", "event")
    ):
        raise WorkflowError("Recover the genuine original one-use learning source")


def available(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    rule_id: str,
    action_id: str | None = None,
) -> LearnedPlayUse | None:
    """Positive canonical lesson, never another person's book or reservation."""
    if rule_id not in SUPPORTED or actor.kind != "pilot":
        return None
    sheet = state.sheets.get(actor.entity)
    if sheet is None or sheet.character_id != actor.incarnation:
        return None
    runtime = sheet.girl_runtime
    for value in runtime.learned_plays if runtime else ():
        if (
            value.actor != actor
            or value.rule_id != rule_id
            or value.rolled_event is not None
            or value.claimed_action not in (None, action_id)
        ):
            continue
        _prove(game, c, state, value)
        if value.claimed_action is not None:
            from girlframe.services.m3_handler_advancements import _history

            action = game.action(c, value.claimed_action)
            meta = action["data"].get("learned_play", {})
            born = _history(c, game, meta.get("event", ""))
            saved = born.sheets.get(actor.entity)
            original = saved.girl_runtime if saved else None
            if (
                str(action["actor_id"]) != actor.entity
                or action["data"]["prepared"]["play"] != SUPPORTED[rule_id][0]
                or meta.get("id") != value.id
                or meta.get("rule_id") != rule_id
                or original is None
                or value not in original.learned_plays
            ):
                raise WorkflowError("Recover this original lesson's own canonical reservation")
        return value
    return None


def claim(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    event: str,
) -> bool:
    play = action["data"]["play"]
    rule = next((rule for rule, (name, _) in SUPPORTED.items() if name == play), None)
    if rule is None:
        return False
    actor = current_ref(state, int(action["actor_id"]))
    sheet = state.sheets[actor.entity]
    runtime = sheet.girl_runtime or GirlRuntime()
    # An actual native/permanent ability does not spend an unrelated temporary lesson.
    permanent = sheet.model_copy(
        update={"girl_runtime": runtime.model_copy(update={"learned_plays": ()})}
    )
    if has_rule(permanent, rule, SUPPORTED[rule][1]):
        return False
    candidates = [
        x
        for x in runtime.learned_plays
        if x.rule_id == rule
        and x.actor == actor
        and x.rolled_event is None
        and x.claimed_action in (None, action["id"])
    ]
    if not candidates:
        raise WorkflowError("This one-use Play is already spent or reserved by its actual source")
    value = candidates[0]
    _prove(game, c, state, value)
    claimed = value.model_copy(update={"claimed_action": action["id"]})
    _replace(state, claimed)
    action["data"]["learned_play"] = dict(id=value.id, event=event, rule_id=rule)
    return True


def consume(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    event: str,
) -> None:
    meta = action["data"].get("learned_play")
    if meta is None:
        return
    actor = current_ref(state, int(action["actor_id"]))
    runtime = state.sheets[actor.entity].girl_runtime
    value = (
        next((x for x in runtime.learned_plays if x.id == meta["id"]), None) if runtime else None
    )
    if value is None or value.claimed_action != action["id"]:
        raise WorkflowError("Recover the actual original reserved learned Play")
    _prove(game, c, state, value)
    if value.rolled_event is not None:
        if value.rolled_event != event:
            raise WorkflowError("Reuse the known receipt; never consume a second learned Play")
        return
    if not action["data"].get("receipt"):
        raise WorkflowError("Consume this lesson only with its actual committed roll")
    _replace(state, value.model_copy(update={"rolled_event": event}))


def release_unrolled(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    """Cancel only the original unrolled reservation after canonical recovery validation."""
    meta = action["data"].get("learned_play")
    if meta is None:
        return False
    if action["data"].get("receipt"):
        raise WorkflowError("A committed learned Play cannot be refunded.")
    actor = current_ref(state, int(action["actor_id"]))
    runtime = state.sheets[actor.entity].girl_runtime
    value = (
        next((x for x in runtime.learned_plays if x.id == meta["id"]), None) if runtime else None
    )
    if (
        value is None
        or value.actor != actor
        or value.claimed_action != action["id"]
        or value.rolled_event is not None
    ):
        raise WorkflowError("Recover this original unrolled learning reservation.")
    _prove(game, c, state, value)
    _replace(state, value.model_copy(update={"claimed_action": None}))
    return True


def prove_consumed(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    rule_id: str,
    roll_event: str,
) -> bool:
    """Prove this exact spent lesson; never restore its admission for another roll."""
    meta = action["data"].get("learned_play")
    if meta is None:
        return False
    from girlframe.services.m3_handler_advancements import _history

    rolled = _history(c, game, roll_event)
    claimed = _history(c, game, meta["event"])
    actor = current_ref(rolled, int(action["actor_id"]))

    def saved(source: GameState) -> LearnedPlayUse | None:
        sheet = source.sheets.get(actor.entity)
        runtime = sheet.girl_runtime if sheet else None
        return (
            next((x for x in runtime.learned_plays if x.id == meta["id"]), None)
            if runtime
            else None
        )

    value, birth, reservation = saved(state), saved(rolled), saved(claimed)
    receipt = (
        c.execute(
            sa.select(t.m2["m2_receipts"]).where(
                t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_receipts"].c.action_id == action["id"],
            )
        )
        .mappings()
        .first()
    )
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == roll_event
            )
        )
        .mappings()
        .first()
    )
    if (
        rule_id not in SUPPORTED
        or meta.get("rule_id") != rule_id
        or action["data"]["prepared"]["play"] != SUPPORTED[rule_id][0]
        or value is None
        or birth is None
        or reservation is None
        or value != birth
        or value.actor != actor
        or value.rule_id != rule_id
        or value.claimed_action != action["id"]
        or value.rolled_event != roll_event
        or reservation != value.model_copy(update={"rolled_event": None})
        or receipt is None
        or json.loads(receipt["body_json"]) != action["data"].get("receipt")
        or event is None
        or event["kind"] not in ("m2.rolled", "m3.rolled")
        or event["actor_id"] != str(action["actor_id"])
        or json.loads(event["payload_json"]).get("action_id") != action["id"]
        or json.loads(event["payload_json"]).get("receipt_id") != receipt["id"]
    ):
        raise WorkflowError(
            "Recover this original lesson's actual reservation and consumed receipt"
        )
    _prove(game, c, rolled, value)
    return True
