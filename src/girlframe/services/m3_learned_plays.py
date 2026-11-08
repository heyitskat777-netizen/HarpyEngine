"""Finite actual learned-Play admission and one-roll consumption; source effects stay explicit."""

from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_girl_runtime_state import GirlRuntime, has_rule
from girlframe.engine.m3_learned_play_state import LearnedPlayUse
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError

SUPPORTED = {"girl.alpha.brutalize": ("brutalize", "ALPHA")}


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
