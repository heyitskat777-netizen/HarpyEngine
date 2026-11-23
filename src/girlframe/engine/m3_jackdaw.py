"""A Jackdaw's audible range and effects on actual original bodies."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_world_state import Cell

RULE = "gorgon-type.jackdaw.jackdaw-type"
KIND = "jackdaw_jam"
EFFECTS = ("jackdaw_jam", "jackdaw_catatonia")


class Range(Model):
    cells: tuple[Cell, ...] = Field(min_length=1)


class Interference(Model):
    actor: ActorRef
    origin: Cell
    range: Range
    action: str
    scene: str
    event: str
    effect: Literal["audible", "catatonia"] = Field(
        default="audible", exclude_if=lambda value: value == "audible"
    )
    victims: tuple[ActorRef, ...] = Field(default=(), exclude_if=lambda value: not value)


def check(state: GameState, actor: ActorRef, origin: Cell | None, extent: Range) -> Cell:
    world = state.world
    if (
        actor.kind != "gorgon"
        or world is None
        or origin is None
        or origin not in extent.cells
        or len(set(extent.cells)) != len(extent.cells)
        or not all(world.board.contains(cell) for cell in extent.cells)
        or not any(x.id == actor.entity and x.alive and "jackdaw" in x.types for x in world.gorgons)
    ):
        raise ValueError(
            "Use the actual Jackdaw and distinct in-range map squares including its origin"
        )
    return origin


def apply(
    state: GameState,
    actor: ActorRef,
    origin: Cell | None,
    extent: Range,
    *,
    action: str,
    scene: str,
    event: str,
    victims: tuple[ActorRef, ...] = (),
) -> Interference:
    original = check(state, actor, origin, extent)
    entry = Interference(
        actor=actor,
        origin=original,
        range=extent,
        action=action,
        scene=scene,
        event=event,
        effect="catatonia" if victims else "audible",
        victims=victims,
    )
    state.facts.append(dict(kind=KIND, id=entry.event, body=entry.model_dump_json()))
    return entry


def ranges(state: GameState) -> tuple[Interference, ...]:
    latest: dict[ActorRef, Interference] = {}
    catatonia = []
    for fact in state.facts:
        if fact.get("kind") == KIND:
            entry = Interference.model_validate_json(fact["body"])
            if entry.effect == "catatonia":
                catatonia.append(entry)
            else:
                latest[entry.actor] = entry
    return (*latest.values(), *catatonia)
