"""The original Harpy's private arrival, draw, and disclosure to the Handler."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_world_state import Cell

RULE = "strain.void.high.2.2"
KIND = "void_bunk_harpy"


class Encounter(Model):
    id: str
    source: str
    period: str
    handler: ActorRef
    harpy: ActorRef
    controller: int
    base: str
    cell: Cell
    population: tuple[ActorRef, ...]
    index: int = Field(ge=0)
    rng_source: Literal["os", "test_injected"]
    arrived: str | None = None
    appearance: str = Field(default="", max_length=900)
    method: Literal["contact", "late"] | None = None
    disclosed: str | None = None
    disclosure: str = Field(default="", max_length=900)

    @model_validator(mode="after")
    def original_draw(self) -> "Encounter":
        if self.index >= len(self.population) or len(set(self.population)) != len(self.population):
            raise ValueError("Record one original draw from distinct eligible Girls")
        return self

    @property
    def girl(self) -> ActorRef:
        return self.population[self.index]


def encounters(state: GameState) -> tuple[Encounter, ...]:
    return tuple(
        Encounter.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def save(state: GameState, encounter: Encounter) -> None:
    state.facts = [
        x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, encounter.id)
    ] + [dict(kind=KIND, id=encounter.id, body=encounter.model_dump_json())]
