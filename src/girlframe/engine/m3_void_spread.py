"""Retain the rolled and selected scope of High Void 2.1."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world import distance
from girlframe.engine.m3_world_state import Board, Cell, Model
from girlframe.engine.rolls import Face

RULE = "strain.void.high.2.1"
KIND = "void_spread_application"
Role = Literal["girl", "handler", "npc", "harpy", "unsupported"]


class Spread(Model):
    faces: tuple[Face, Face]
    rng_source: Literal["os", "test_injected"]
    roll_event: str
    cells: tuple[Cell, ...] = Field(default=(), max_length=12)
    scope_event: str | None = None


class Occupant(Model):
    actor: ActorRef
    label: str
    controller: int
    role: Role
    cell: Cell
    work: str


class Application(Model):
    id: str
    scope: str
    event: str
    handler: ActorRef
    occupants: tuple[Occupant, ...]
    reviewed_outside: tuple[ActorRef, ...] = ()


def applications(state: GameState) -> tuple[Application, ...]:
    return tuple(
        Application.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def select(board: Board, spread: Spread, cells: tuple[Cell, ...], event: str) -> Spread:
    pending = set(cells)
    if (
        spread.scope_event is not None
        or len(cells) != sum(spread.faces)
        or len(pending) != len(cells)
        or any(not board.contains(cell) for cell in cells)
    ):
        raise ValueError("Use the saved total of distinct squares on the actual map")
    connected = {pending.pop()}
    while pending:
        adjacent = {cell for cell in pending if any(distance(cell, x) == 1 for x in connected)}
        if not adjacent:
            raise ValueError("Choose connected squares using the ordinary map adjacency")
        connected.update(adjacent)
        pending.difference_update(adjacent)
    return spread.model_copy(update={"cells": cells, "scope_event": event})
