"""Original-character career history, distinct from the account's stable draft profile."""

from typing import Literal

from pydantic import Field

from girlframe.engine.identity import Snowflake
from girlframe.engine.m3_actor_state import ActorRef, Model

Ending = Literal["death", "execution", "imprisonment", "retirement", "reserve", "harpy"]


class CareerArchive(Model):
    id: str = Field(min_length=1, max_length=100)
    actor: ActorRef
    ending: Ending
    source_event: str = Field(min_length=1)
    account: str = Field(min_length=1, max_length=1200)
    profile_id: str = Field(min_length=1)
    profile_revision: int = Field(ge=1)
    position: int = Field(ge=0)
    sheet_json: str = Field(min_length=1)
    links_json: str = Field(min_length=1)


class IncarnationBinding(Model):
    owner: Snowflake
    character: str = Field(min_length=1, max_length=100)
    profile_id: str = Field(min_length=1)
    first_profile_revision: int = Field(ge=1)
    source_event: str = Field(min_length=1)
    active: bool
    previous_archive: str | None = None
    status_position: int | None = Field(default=None, ge=0)
    status_event: str | None = None


class UnlinkedCareer(Model):
    actor: ActorRef
    source_event: str = Field(min_length=1)
    account: str = Field(min_length=1, max_length=1200)
    frame_json: str = Field(min_length=1)


class CareerReturn(Model):
    id: str = Field(min_length=1)
    archive: str = Field(min_length=1)
    owner: Snowflake
    handler: Snowflake
    handler_persona: str | None = None
    source_event: str = Field(min_length=1)
    current_character: str
    other_characters: tuple[ActorRef, ...]
    position: int = Field(ge=0)
    account: str = Field(min_length=1, max_length=1200)
    state: Literal["offered", "declined", "withdrawn", "returned"] = "offered"
    response_event: str | None = None
