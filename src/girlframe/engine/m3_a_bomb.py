"""Actual nuclear drops and original resource rosters, never a weapon actor or fake Core."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_world_state import Cell

RULE = "handler-advancement.handler-advancement.a-bomb"
Option = Literal["safe_ejection", "cores", "gentle_fallout", "mission_budget"]
OPTIONS: tuple[Option, ...] = ("safe_ejection", "cores", "gentle_fallout", "mission_budget")


class Acquisition(Model):
    id: str
    award: str
    handler: ActorRef
    appointment: str
    event: str
    account: str


class Resource(Model):
    actor: ActorRef
    controller: int
    family: Literal["frame", "gorgon"]
    frame: str | None = None
    vessel: str | None = None
    cell: Cell
    assets: tuple[str, ...]
    original: str
    losses: tuple[str, ...] = ()
    event: str | None = None
    work: tuple[str, ...] = ()


class Drop(Model):
    id: str
    acquisition: str
    handler: ActorRef
    appointment: str
    event: str
    device: str
    device_json: str
    release: Cell
    centre: Cell
    cells: tuple[Cell, ...]
    options: tuple[Option, Option]
    delivery: str = Field(min_length=1, max_length=1200)
    judge: int
    judge_appointment: str
    resources: tuple[Resource, ...]
    npcs: dict[str, str]
    sprites: dict[str, str]
    deaths: tuple[ActorRef, ...]
    structures: tuple[str, ...]
    breaches: dict[str, str] = Field(default_factory=dict)
    mission: str | None = None
    mission_objective: str | None = None
    causal: bool | None = None
    causal_event: str | None = None
    causal_account: str | None = None
    mission_resolved_event: str | None = None
    initial_event: str | None = None
    completed_event: str | None = None
    loss: str | None = None


def acquisitions(state: GameState) -> tuple[Acquisition, ...]:
    return tuple(
        Acquisition.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "a_bomb_acquisition"
    )


def drops(state: GameState) -> tuple[Drop, ...]:
    return tuple(
        Drop.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == "a_bomb_drop"
    )


def put(state: GameState, value: Acquisition | Drop) -> None:
    kind = "a_bomb_acquisition" if isinstance(value, Acquisition) else "a_bomb_drop"
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))


def footprint(centre: Cell) -> tuple[Cell, ...]:
    return tuple((centre[0] + x, centre[1] + y) for x in (-1, 0, 1) for y in (-1, 0, 1))


def radiation_drops(state: GameState, owner: ActorRef, frame: str, cell: Cell) -> tuple[Drop, ...]:
    sheet = state.sheets.get(owner.entity) if owner.kind == "pilot" else None
    if (
        sheet is None
        or sheet.character_id != owner.incarnation
        or any(x.family == "frame" and not x.damaged for x in sheet.assets)
    ):
        return ()
    active = (
        {x.id for x in state.world.fallout if x.expired_event is None and cell in x.cells}
        if state.world
        else set()
    )
    return tuple(
        value
        for value in drops(state)
        if value.id in active
        and any(x.actor == owner and x.frame == frame for x in value.resources)
    )


def exit_fact(
    state: GameState,
    actor: ActorRef,
    vessel: str,
    frame: str | None,
    owner: ActorRef | None,
    cell: Cell,
    event: str,
) -> None:
    if owner is None or frame is None or not radiation_drops(state, owner, frame, cell):
        return
    state.facts.append(
        dict(
            kind="a_bomb_actual_exit",
            actor=actor.model_dump_json(),
            vessel=vessel,
            frame=frame,
            owner=owner.model_dump_json(),
            cell=str(cell),
            event=event,
        )
    )


class Device(Model):
    id: str
    acquisition: str
    item: str
    item_json: str
    handler: ActorRef
    appointment: str
    event: str
    cell: Cell
    capability: Literal["nuclear"] = "nuclear"
    account: str = Field(min_length=1, max_length=1200)


def devices(state: GameState) -> tuple[Device, ...]:
    return tuple(
        Device.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "a_bomb_device"
    )
