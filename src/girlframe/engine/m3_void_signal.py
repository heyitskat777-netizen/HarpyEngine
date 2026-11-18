"""The original draw and owned Void gain from High Void 5, column 2."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model

RULE = "strain.void.high.5.2"
KIND = "strain_void_signal"


class Signal(Model):
    id: str
    source_event: str
    gorgon: str
    people: tuple[ActorRef, ...] = Field(min_length=1)
    index: int = Field(ge=0)
    rng: Literal["os", "test_injected"]
    gain_event: str | None = None
    asset: str | None = None
    thresholds: tuple[str, ...] = ()

    @model_validator(mode="after")
    def original_draw(self) -> "Signal":
        if self.index >= len(self.people) or len({x.entity for x in self.people}) != len(
            self.people
        ):
            raise ValueError("Preserve one actual draw from the original distinct Girls")
        return self

    @property
    def actor(self) -> ActorRef:
        return self.people[self.index]


def signals(state: GameState) -> tuple[Signal, ...]:
    return tuple(
        Signal.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def put(state: GameState, record: Signal) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, record.id)] + [
        dict(kind=KIND, id=record.id, body=record.model_dump_json())
    ]
