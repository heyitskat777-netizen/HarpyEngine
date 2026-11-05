"""Three actual Handler choices; no imaginary Girl Assets or automatic institutional actions."""

from typing import Any
from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_handler_void_state import HandlerVoid


def require(
    state: GameState, actor: ActorRef, *, work: str, source_event: str, appointment: str
) -> tuple[GameState, str]:
    body = active_handler(state)
    controller = None
    if actor.kind == "npc":
        actual = (
            next((x for x in state.world.npcs if x.id == actor.entity), None)
            if state.world
            else None
        )
        if actual is None or not actual.alive or "director" not in actual.jobs:
            raise ValueError("Only the actual living Director body uses Handler Void rules")
        body, controller = actor, actual.controller
    elif (
        body is None
        or not same_handler_body(state, actor)
        or any(x.active and x.handler == int(actor.entity) for x in state.director_contexts)
    ):
        raise ValueError("Only the actual normal Handler body uses this physiological rule")
    else:
        controller = int(actor.entity)
    assert body is not None and controller is not None
    identity = str(uuid5(NAMESPACE_URL, "girlframe:handler-void:" + work + ":" + actor.token))
    existing = next((x for x in state.handler_void if x.work == work), None)
    if existing:
        if (
            existing.id != identity
            or existing.actor != actor
            or existing.source_event != source_event
        ):
            raise ValueError("This actual Handler Void source already belongs to another original")
        return state, identity
    changed = GameState.model_validate_json(state.model_dump_json())
    changed.handler_void.append(
        HandlerVoid(
            id=identity,
            actor=actor,
            body=body,
            controller=controller,
            work=work,
            source_event=source_event,
            appointment=appointment,
        )
    )
    return changed, identity


def choose(
    original: GameState,
    identity: str,
    choice: str,
    event: str,
    *,
    account: str,
    site: str = "",
    manifestation: str | None = None,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    episode = next((x for x in state.handler_void if x.id == identity), None)
    if episode is None or episode.phase not in ("choice", "stabilized") or not account.strip():
        raise ValueError("Choose the actual original Handler's still-owned corruption consequence")
    if (
        choice not in ("knife", "drugs", "surgery")
        or episode.phase == "stabilized"
        and choice == "drugs"
    ):
        raise ValueError(
            "Stabilized corruption still needs actual removal, not repeated free drugs"
        )
    values: dict[str, Any] = dict(
        choice=choice,
        choice_event=event,
        account=account.strip(),
        site=site.strip() or episode.site,
    )
    if choice == "knife":
        values.update(
            phase="removed", void_present=False, removal_event=event, wound=account.strip()
        )
    elif choice == "drugs":
        values.update(
            phase="stabilized", spread_halted=True, manifestation=manifestation, site=site.strip()
        )
    else:
        values.update(phase="surgery")
    updated = HandlerVoid.model_validate_json(episode.model_copy(update=values).model_dump_json())
    state.handler_void = [updated if x.id == identity else x for x in state.handler_void]
    return state


def surgery(original: GameState, identity: str, event: str, account: str) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    episode = next((x for x in state.handler_void if x.id == identity), None)
    if episode is None or episode.phase != "surgery" or not account.strip():
        raise ValueError("Record the actual requested and performed surgery, not an acknowledgment")
    updated = episode.model_copy(
        update={
            "phase": "removed",
            "void_present": False,
            "removal_event": event,
            "surgery_account": account.strip(),
        }
    )
    state.handler_void = [
        HandlerVoid.model_validate_json(updated.model_dump_json()) if x.id == identity else x
        for x in state.handler_void
    ]
    return state


def end_actor(original: GameState, actor: ActorRef, event: str) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    state.handler_void = [
        x.model_copy(update={"phase": "ended", "ended_event": event})
        if actor in (x.actor, x.body) and x.phase not in ("removed", "ended")
        else x
        for x in state.handler_void
    ]
    return state
