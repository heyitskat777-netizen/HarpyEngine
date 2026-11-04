"""Typed runtime Frame setup and reviewed compulsory replacement packages."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from girlframe.engine.fanbase import Fanbase
from girlframe.engine.frame_setup import HarpyCore
from girlframe.engine.identity import Snowflake


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Preferences(Model):
    frame: str = Field(max_length=80)
    frame_name: str = Field(default="", max_length=120)
    frame_appearance: str = Field(default="", max_length=700)
    fanbase: Fanbase | None = None
    court_role: (
        Literal["The Queen", "The Consort", "The Knight", "The Doll", "The Traitor"] | None
    ) = None
    court_target: Snowflake | None = None


class SuppliedAsset(Model):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=700)
    damaged: bool
    void: bool

    @model_validator(mode="after")
    def nonblank(self) -> "SuppliedAsset":
        if not self.name.strip() or not self.description.strip():
            raise ValueError("Name and describe every supplied Asset")
        return self


class Package(Model):
    assets: tuple[SuppliedAsset, ...] = Field(max_length=5)
    additional_rules: tuple[str, ...] = ()
    consume_hunger: Literal["Quiet", "Gnawing", "Ravenous"] | None = None
    obsolescence_marked: int | None = Field(default=None, ge=0, le=7)
    psych_strings: tuple[Snowflake, ...] = ()
    explanation: str = Field(min_length=1, max_length=1200)


class FrameRuntime(Model):
    id: str = Field(min_length=1, max_length=80)
    generation: int = Field(ge=1)
    source_work: str
    frame_name: str = ""
    frame_appearance: str = ""
    core_id: str | None = None
    harpy_core: HarpyCore | None = None
    fanbase: Fanbase | None = None
    court: dict[str, Snowflake] = Field(default_factory=dict)
    consume_hunger: Literal["Quiet", "Gnawing", "Ravenous"] | None = None
    psych_strings: tuple[Snowflake, ...] = ()
    acquired_rules: tuple[str, ...] = ()
