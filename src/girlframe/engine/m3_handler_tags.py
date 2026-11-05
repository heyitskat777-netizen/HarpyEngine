"""A Girl spends an actual Handler Tag; a favour never grants a mechanical reward."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, Model, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_world_state import Npc

Kind = Literal["favour", "attention", "compel"]
Response = Literal["agree", "decline", "pause", "give_in", "original_handler_ended"]


class Use(Model):
    id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    girl: ActorRef
    girl_controller: int = Field(gt=0)
    handler: ActorRef
    handler_controller: int = Field(gt=0)
    tag: str = Field(min_length=1)
    tag_label: str = Field(min_length=1)
    kind: Kind
    account: str = Field(min_length=1, max_length=1200)
    source_event: str = Field(min_length=1)
    scene: str = Field(min_length=1)
    state: Literal["pending", "resolved"]
    response: Response | None = None
    response_account: str = Field(default="", max_length=1200)
    response_event: str | None = None


def uses(state: GameState) -> tuple[Use, ...]:
    latest: dict[str, Use] = {}
    for fact in state.facts:
        if fact.get("kind") != "handler_tag_use":
            continue
        entry = Use.model_validate_json(fact["body"])
        previous = latest.get(entry.id)
        if entry.revision != (previous.revision + 1 if previous else 1):
            raise ValueError("Recover the original append-only Handler Tag use history")
        latest[entry.id] = entry
    return tuple(latest.values())


def save(state: GameState, value: Use) -> None:
    state.facts.append(dict(kind="handler_tag_use", body=value.model_dump_json()))


def director(state: GameState, actor: ActorRef) -> Npc | None:
    return (
        next(
            (
                x
                for x in state.world.npcs
                if actor.kind == "npc" and x.id == actor.entity and x.alive and "director" in x.jobs
            ),
            None,
        )
        if state.world
        else None
    )


def current(state: GameState, actor: ActorRef) -> bool:
    return (
        same_handler_body(state, actor)
        if actor.kind == "handler"
        else director(state, actor) is not None
    )


def girl_rules(actual: ActorView) -> bool:
    return (
        actual.rules == "handler_girl"
        or actual.ref.kind in ("pilot", "external_pilot")
        and bool(actual.girl)
    )


def consume(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    girl: ActorRef,
    tag: str,
    kind: Kind,
    account: str,
    identity: str,
    event: str,
    scene: str,
    *,
    handler_ref: ActorRef | None = None,
) -> tuple[GameState, Use]:
    state = GameState.model_validate_json(original.model_dump_json())
    actual = resolve(state, girl, bindings, require_current_profile=False)
    handler = handler_ref or active_handler(state)
    if handler is None or not girl_rules(actual):
        raise ValueError("An actual living Girl must address the actual original Handler")
    npc = director(state, handler)
    if not current(state, handler):
        raise ValueError("Use the actual current Handler body or a real living Director")
    if (
        girl.kind == "handler"
        and handler.kind == "handler"
        and same_handler_body(state, girl)
        and same_handler_body(state, handler)
    ):
        raise ValueError(
            "Your temporary Girl rules do not create a second body to address yourself"
        )
    target_controller = npc.controller if npc else int(handler.entity)
    selected = next((x for x in (npc.tags if npc else state.handler_tags) if x.id == tag), None)
    visible = (
        npc.revealed or npc.controller == actual.controller
        if npc
        else isinstance(selected, TagState) and actual.controller in selected.observers
    )
    if selected is None or not visible:
        raise ValueError("Choose an actual Handler Tag this Girl's human has observed")
    if kind not in ("favour", "attention", "compel") or not account.strip():
        raise ValueError("Choose a printed Handler Tag use and describe the actual request")
    if not identity or not event or not scene or any(x.id == identity for x in uses(state)):
        raise ValueError("Use a fresh actual source event and original scene")
    value = Use(
        id=identity,
        revision=1,
        girl=girl,
        girl_controller=actual.controller,
        handler=handler,
        handler_controller=target_controller,
        tag=tag,
        tag_label=selected.label,
        kind=kind,
        account=account.strip(),
        source_event=event,
        scene=scene,
        state="resolved" if kind == "attention" else "pending",
        response_event=event if kind == "attention" else None,
    )
    if npc is not None:
        assert state.world is not None
        state.world = state.world.model_copy(
            update={
                "npcs": tuple(
                    x.model_copy(update={"tags": tuple(t for t in x.tags if t.id != tag)})
                    if x.id == npc.id
                    else x
                    for x in state.world.npcs
                )
            }
        )
    else:
        state.handler_tags = [x for x in state.handler_tags if x.id != tag]
    for obligation in state.obligations:
        if (
            obligation.kind != "actor_reject_tag"
            or handler.kind != "handler"
            or obligation.state != "pending"
            or obligation.details.get("tag") != tag
        ):
            continue
        ref_json = obligation.details.get("actor")
        if ref_json is None:
            continue
        bearer = ActorRef.model_validate_json(ref_json)
        if bearer.kind == "handler" and same_handler_body(state, bearer):
            obligation.state = "fulfilled"
            obligation.details.update(resolved_by_handler_tag_use=identity, resolved_event=event)
    save(state, value)
    return state, value


def respond(
    original: GameState,
    identity: str,
    expected: int,
    response: Response,
    account: str,
    event: str,
    *,
    ended_source: bool = False,
) -> tuple[GameState, Use]:
    state = GameState.model_validate_json(original.model_dump_json())
    value = next((x for x in uses(state) if x.id == identity), None)
    if value is None or value.state != "pending" or value.revision != expected:
        raise ValueError("Refresh the actual original Handler Tag request")
    live = current(state, value.handler)
    if response == "original_handler_ended":
        if live or not ended_source:
            raise ValueError("Prove the actual original Handler ending before closing its request")
    elif not live or response not in (
        ("agree", "decline") if value.kind == "favour" else ("pause", "give_in")
    ):
        raise ValueError("The original Handler chooses only this request's printed response")
    if not account.strip() or not event:
        raise ValueError("The actual Handler must describe its own response")
    result = value.model_copy(
        update=dict(
            revision=value.revision + 1,
            state="resolved",
            response=response,
            response_account=account.strip(),
            response_event=event,
        )
    )
    save(state, result)
    return state, result
