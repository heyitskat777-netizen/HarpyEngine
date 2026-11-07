"""Paid body-bound collars and exact triggered survival sources, outside ordinary Tags."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

RULE = "handler-advancement.handler-advancement.bomb-collar"


class Acquisition(Model):
    id: str
    award: str
    handler: ActorRef
    appointment: str
    event: str
    account: str = Field(min_length=1, max_length=1200)


class Collar(Model):
    id: str
    acquisition: str
    target: ActorRef
    vessel: str
    event: str
    tag: TagState
    trigger: str | None = None


class Trigger(Model):
    id: str
    collar: str
    target: ActorRef
    vessel: str
    handler: ActorRef
    appointment: str
    event: str
    cast: SceneCast
    account: str = Field(min_length=1, max_length=1200)
    phase: Literal["survival", "survived", "death", "prevented", "ended"] = "survival"
    action: str | None = None
    result_event: str | None = None
    effect_event: str | None = None
    archive: str | None = None


def acquisitions(state: GameState) -> tuple[Acquisition, ...]:
    return tuple(
        Acquisition.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "bomb_collar_acquisition"
    )


def collars(state: GameState) -> tuple[Collar, ...]:
    return tuple(
        Collar.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == "bomb_collar"
    )


def triggers(state: GameState) -> tuple[Trigger, ...]:
    return tuple(
        Trigger.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "bomb_collar_trigger"
    )


def put(state: GameState, value: Acquisition | Collar | Trigger) -> None:
    kind = {
        Acquisition: "bomb_collar_acquisition",
        Collar: "bomb_collar",
        Trigger: "bomb_collar_trigger",
    }[type(value)]
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))


def tags(state: GameState, owner: int) -> list[TagState]:
    if str(owner) not in state.sheets:
        return []
    return [
        x.tag for x in collars(state) if x.target == current_ref(state, owner) and x.trigger is None
    ]


def save_tag(state: GameState, owner: int, tag: TagState) -> bool:
    if not tag.id.startswith("bomb-collar:"):
        return False
    value = next(x for x in collars(state) if x.id == tag.id)
    if value.target != current_ref(state, owner) or value.trigger is not None:
        raise ValueError("Use only the actual original body's untriggered collar")
    if tag.rejection_pending:
        raise ValueError("A bomb collar cannot be embraced or rejected")
    put(state, value.model_copy(update=dict(tag=tag)))
    return True
