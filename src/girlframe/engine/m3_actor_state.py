"""Fictional actor references are separate from their current human controllers."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from girlframe.engine.identity import Snowflake

Kind = Literal["pilot", "npc", "external_pilot", "gorgon", "handler"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ActorRef(Model):
    kind: Kind
    entity: str = Field(min_length=1, max_length=100)
    incarnation: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def source_identity(self) -> "ActorRef":
        if not self.entity.strip():
            raise ValueError("Use the actual actor's stable entity ID")
        if self.kind in ("pilot", "handler"):
            if (
                not self.entity.isascii()
                or not self.entity.isdecimal()
                or str(int(self.entity)) != self.entity
                or not 0 < int(self.entity) < 2**64
            ):
                raise ValueError("A human PC reference uses its actual numeric owner ID")
        if self.kind == "pilot" and self.incarnation is None:
            raise ValueError("A Pilot reference requires its actual character incarnation")
        if self.kind not in ("pilot", "handler") and self.incarnation is not None:
            raise ValueError("Do not invent a second character generation for a world entity")
        return self

    @property
    def token(self) -> str:
        """A bounded opaque selector key, never a display-name authority claim."""
        return str(uuid5(NAMESPACE_URL, self.model_dump_json()))


class ProfileBinding(Model):
    owner: Snowflake
    character_id: str = Field(min_length=1, max_length=100)
    profile_revision: int = Field(ge=1)
    source_character_id: str | None = Field(default=None, min_length=1, max_length=100)
    source_profile_revision: int | None = Field(default=None, ge=1)


class CastRole(Model):
    actor: ActorRef
    controller: Snowflake
    source_event: str = Field(min_length=1)


class SceneCast(Model):
    id: str = Field(min_length=1)
    channel: Snowflake
    revision: int = Field(default=1, ge=1)
    open: bool = True
    roles: tuple[CastRole, ...] = ()
    facilitator: Snowflake | None = None
    facilitator_source: str | None = None
    adjudicator: ActorRef | None = None

    @model_validator(mode="after")
    def actual_roles(self) -> "SceneCast":
        if len({x.actor for x in self.roles}) != len(self.roles):
            raise ValueError("A real actor has one casting record in a scene")
        handlers = [x.actor.entity for x in self.roles if x.actor.kind == "handler"]
        if len(handlers) != len(set(handlers)):
            raise ValueError("A Handler's changed rules context does not create another body")
        if (self.facilitator is None) != (self.facilitator_source is None):
            raise ValueError("A facilitator needs their actual explicit join provenance")
        if self.adjudicator is not None and (
            self.adjudicator.kind != "npc"
            or not any(x.actor == self.adjudicator for x in self.roles)
        ):
            raise ValueError("A Director adjudicator needs its actual NPC cast role")
        return self


class AssetView(Model):
    id: str
    name: str
    family: Literal["girl", "frame", "gorgon"]
    damaged: bool
    void: bool
    counts_toward_limit: bool | None = None
    can_replace_at_limit: bool | None = None


class IdentityView(Model):
    id: str
    name: str
    marked: bool
    protected: bool
    paired: bool
    slot: int | None


class ActorView(Model):
    ref: ActorRef
    controller: Snowflake
    label: str
    alive: bool
    rules: Literal[
        "girl_frame", "npc", "director", "external_pilot", "gorgon", "handler", "handler_girl"
    ]
    girl: str | None = None
    frame: str | None = None
    frame_instance: str | None = None
    frame_scrapped: bool | None = None
    heat: int | None = Field(default=None, ge=0)
    assets: tuple[AssetView, ...] = ()
    identities: tuple[IdentityView, ...] = ()
    jobs: tuple[str, ...] = ()
    cell: tuple[int, int] | None = None
    vessel_id: str | None = None
    frame_cell: tuple[int, int] | None = None
    inside_frame: bool | None = None
    piloting: bool | None = None
    occupied_frame_instance: str | None = None
    position_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    core_exposed: bool | None = None
    custody: str | None = None
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
