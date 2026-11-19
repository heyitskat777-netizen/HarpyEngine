"""A new actual Handler Tag opens one unused printed Crisis Management choice."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_strain_state import Track

RULE = "handler-playbook.frantic.crisis-management"
RaiseSlot = Literal["raise_first", "raise_second"]
RAISE_SLOTS: tuple[RaiseSlot, ...] = ("raise_first", "raise_second")
BreakSlot = Literal["break_first", "break_second"]
BREAK_SLOTS: tuple[BreakSlot, ...] = ("break_first", "break_second")
RuinSlot = Literal["city", "base_first", "base_second", "base_third"]
RUIN_SLOTS: tuple[RuinSlot, ...] = ("city", "base_first", "base_second", "base_third")


class Crisis(Model):
    id: str
    handler: ActorRef
    tag: str
    source_event: str
    slot: RaiseSlot | BreakSlot | RuinSlot | None = None
    track: Track | None = None
    breakdown: str | None = Field(default=None, exclude_if=lambda value: value is None)
    location: str | None = Field(default=None, exclude_if=lambda value: value is None)
    effect_event: str | None = None

    @model_validator(mode="after")
    def exact(self) -> "Crisis":
        pending = self.slot is None
        if (
            self.handler.kind != "handler"
            or (self.track is not None) != (self.slot in RAISE_SLOTS)
            or (self.breakdown is not None) != (self.slot in BREAK_SLOTS)
            or (self.location is not None) != (self.slot in RUIN_SLOTS)
            or (self.effect_event is None) != pending
        ):
            raise ValueError(
                "Keep the exact Frantic, source Tag and actual use of the printed slot"
            )
        return self


def records(state: GameState) -> tuple[Crisis, ...]:
    return tuple(
        Crisis.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "frantic_crisis"
    )


def put(state: GameState, value: Crisis) -> None:
    state.facts = [
        x for x in state.facts if x.get("kind") != "frantic_crisis" or x.get("id") != value.id
    ]
    state.facts.append(dict(kind="frantic_crisis", id=value.id, body=value.model_dump_json()))
