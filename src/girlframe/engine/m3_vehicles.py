"""Actual placed regular vehicles are objects, not proxy characters or Vital Frames."""

from typing import Literal

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import Model
from girlframe.engine.m3_world_state import Cell


class Vehicle(Model):
    id: str
    name: str
    description: str
    cell: Cell
    scene: str
    assessed_by: int
    event: str
    occupancy: Literal["empty", "occupied", "unknown"]
    destroyed_event: str | None = None
    source_action: str | None = None


def vehicles(state: GameState) -> tuple[Vehicle, ...]:
    return tuple(
        Vehicle.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "regular_vehicle"
    )


def put(state: GameState, vehicle: Vehicle) -> None:
    state.facts = [
        x
        for x in state.facts
        if not (x.get("kind") == "regular_vehicle" and x.get("id") == vehicle.id)
    ] + [dict(kind="regular_vehicle", id=vehicle.id, body=vehicle.model_dump_json())]
