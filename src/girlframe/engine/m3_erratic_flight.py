"""The original Erratic Gorgon and saved battlefield flight."""

from typing import TYPE_CHECKING

from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_world_state import Cell

if TYPE_CHECKING:
    from girlframe.engine.m2 import GameState


class Flight(Model):
    gorgon: ActorRef
    scene: str
    channel: int
    battle: str
    departure: Cell
    destination: Cell
    event: str
    catcher: ActorRef | None = None
    pursuit: str | None = None
    caught: str | None = None


def flights(state: "GameState") -> dict[str, Flight]:
    values = {}
    for fact in state.facts:
        if fact.get("kind") == "erratic_flight":
            value = Flight.model_validate_json(fact["body"])
            values[value.event] = value
    return values


def active(state: "GameState", target: ActorRef, scene: str) -> Flight | None:
    return next(
        (
            item
            for item in flights(state).values()
            if item.gorgon == target and item.scene == scene and item.caught is None
        ),
        None,
    )


def save(state: "GameState", value: Flight) -> None:
    state.facts.append(dict(kind="erratic_flight", body=value.model_dump_json()))
