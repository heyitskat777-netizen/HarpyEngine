"""Actual Harpy hide/recovery records, distinct from a ranked Cadre period."""

from typing import Literal

from pydantic import Field

from girlframe.engine.identity import Snowflake
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_void_state import HarpyIdentity


class Rest(Model):
    action: str = Field(min_length=1)
    actor: ActorRef
    controller: Snowflake
    source_event: str = Field(min_length=1)
    identities: tuple[HarpyIdentity, ...]
    route: str = Field(min_length=1)
    phase: Literal["proposed", "rejected", "complete", "ended"] = "proposed"
    completion_event: str | None = None
