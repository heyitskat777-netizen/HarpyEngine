"""Immutable Harpy raid premise and the receipt that actually carries it out."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_world_state import Cell

RULE = "strain.void.high.1.1"
KIND = "strain_harpy_raid"


class Raid(Model):
    id: str
    source: str
    base: str
    cell: Cell
    harpy: ActorRef
    controller: int
    handler: ActorRef
    obsession: ActorRef
    defenders: tuple[ActorRef, ...]
    action: str | None = None
    completion: str | None = None


def raids(state: GameState) -> tuple[Raid, ...]:
    return tuple(Raid.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND)


def save(state: GameState, raid: Raid) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, raid.id)] + [
        dict(kind=KIND, id=raid.id, body=raid.model_dump_json())
    ]
