"""Brutalize's Broken belongs to actual originals and its inflictor, not an account."""

from pydantic import Field

from girlframe.engine.m3_actor_state import ActorRef, Model


class Broken(Model):
    id: str = Field(min_length=1)
    subject: ActorRef
    inflictor: ActorRef
    source_action: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    counter: str | None = None
    removed_event: str | None = None
    removed_action: str | None = None
