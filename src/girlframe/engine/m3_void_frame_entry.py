"""One original random Girl, one actual next entry, and an additional Dive modifier."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_physical_state import Placement

RULE = "strain.void.low.1.2"
WORK = "void_frame_entry_dive"
MODIFIER = "strain_void_frame_entry"


def identity(*parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, "girlframe:void-frame-entry:" + ":".join(parts)))


class Selection(Model):
    id: str
    work: str
    source_event: str
    period: str
    handler: int
    population: tuple[ActorRef, ...]
    index: int = Field(ge=0)
    actor: ActorRef
    rng_source: Literal["os", "test_injected"]
    account: str
    event: str


class Entry(Model):
    id: str
    selection: str
    actor: ActorRef
    frame: str
    vessel: str
    before: Placement
    after: Placement
    event: str
    source_action: str | None = Field(default=None, exclude_if=lambda value: value is None)
    cast: SceneCast | None = Field(default=None, exclude_if=lambda value: value is None)
    venue_event: str | None = Field(default=None, exclude_if=lambda value: value is None)
    ready_event: str | None = Field(default=None, exclude_if=lambda value: value is None)
    prerequisites: tuple[str, ...] = ()
    child: str | None = Field(default=None, exclude_if=lambda value: value is None)
    roll_event: str | None = Field(default=None, exclude_if=lambda value: value is None)
    completed_event: str | None = Field(default=None, exclude_if=lambda value: value is None)


class RollUse(Model):
    id: str
    entry: str
    action: str
    actor: ActorRef
    frame: str
    assets: tuple[AssetState, ...]
    amount: int = Field(ge=0)
    event: str


KINDS: dict[type[Model], str] = {
    Selection: "void_frame_entry_selection",
    Entry: "void_frame_entry",
    RollUse: "void_frame_entry_roll",
}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(row["body"])
        for row in state.facts
        if row.get("kind") == KINDS[model]
    )


def get[T: Model](state: GameState, model: type[T], key: str) -> T:
    values = [value for value in records(state, model) if value.model_dump()["id"] == key]
    if len(values) != 1:
        raise ValueError("Recover this original Strain entry source")
    return values[0]


def put(state: GameState, value: Selection | Entry | RollUse) -> None:
    kind = KINDS[type(value)]
    state.facts = [
        row for row in state.facts if not (row.get("kind") == kind and row.get("id") == value.id)
    ]
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))


def due(state: GameState, actor: ActorRef | None = None) -> tuple[Entry, ...]:
    return tuple(
        value
        for value in records(state, Entry)
        if value.completed_event is None and (actor is None or value.actor == actor)
    )


def pause_sources(state: GameState) -> tuple[dict[str, str | int], ...]:
    return tuple(
        dict(
            id=value.id,
            channel=value.cast.channel,
            scene=value.cast.id,
            event=value.venue_event or value.ready_event or value.event,
        )
        for value in due(state)
        if value.cast is not None and value.ready_event
    )
