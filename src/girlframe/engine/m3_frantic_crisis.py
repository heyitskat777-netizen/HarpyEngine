"""A new actual Handler Tag opens one unused printed Crisis Management choice."""

from typing import Literal

from pydantic import model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_strain_state import Track

RULE = "handler-playbook.frantic.crisis-management"
RaiseSlot = Literal["raise_first", "raise_second"]
RAISE_SLOTS: tuple[RaiseSlot, ...] = ("raise_first", "raise_second")


class Crisis(Model):
    id: str
    handler: ActorRef
    tag: str
    source_event: str
    slot: RaiseSlot | None = None
    track: Track | None = None
    effect_event: str | None = None

    @model_validator(mode="after")
    def exact(self) -> "Crisis":
        pending = self.slot is None
        if (
            self.handler.kind != "handler"
            or (self.track is None) != pending
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
