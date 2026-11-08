"""Source-owned relationships belong to fictional people, never their controllers."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import ActorRef, Model


class BondEdge(Model):
    first: ActorRef
    second: ActorRef
    depth: Literal[0, 1, 2]
    source_event: str = Field(min_length=1)

    @model_validator(mode="after")
    def distinct(self) -> "BondEdge":
        if self.first == self.second:
            raise ValueError("A Bond needs two actual distinct people")
        return self


class HelplessCondition(Model):
    id: str = Field(min_length=1)
    subject: ActorRef
    foe: ActorRef
    source_events: tuple[str, ...] = Field(min_length=1)
    active: bool = True
    recovery_event: str | None = None

    @model_validator(mode="after")
    def actual_opponents(self) -> "HelplessCondition":
        if self.subject == self.foe or any(not x.strip() for x in self.source_events):
            raise ValueError("Helplessness requires an actual opponent and source")
        if self.active == (self.recovery_event is not None):
            raise ValueError("Only actual recovery ends Helplessness")
        return self
