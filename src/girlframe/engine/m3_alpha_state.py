"""Brutalize's Broken belongs to actual originals and its inflictor, not an account."""

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import ActorRef, Model


class Broken(Model):
    id: str = Field(min_length=1)
    subject: ActorRef
    inflictor: ActorRef
    source_action: str | None = Field(default=None, min_length=1, exclude_if=lambda x: x is None)
    source_work: str | None = Field(default=None, min_length=1, exclude_if=lambda x: x is None)
    source_event: str = Field(min_length=1)
    counter: str | None = None
    removed_event: str | None = None
    removed_action: str | None = None

    @model_validator(mode="after")
    def exact_source(self) -> "Broken":
        if (self.source_action is None) == (self.source_work is None):
            raise ValueError("Record the actual original Play or other printed source of Broken")
        return self
