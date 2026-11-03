"""Typed, voluntary starting setup choices; no fictional effects implied."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from girlframe.engine.drafts import DraftInput
from girlframe.engine.identity import Snowflake

Kind = Literal["court", "callsign"]
AM_ROLES = ("The Queen", "The Consort", "The Knight", "The Doll", "The Traitor")


class CourtChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    role: Literal["The Queen", "The Consort", "The Knight", "The Doll", "The Traitor"]


class CallsignChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    callsign: str = Field(min_length=1, max_length=32)

    @field_validator("callsign")
    @classmethod
    def label(cls, value: str) -> str:
        return DraftInput.clean_label(value)


class AcceptedSetup(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    id: str
    revision: int
    kind: Kind
    source_id: Snowflake
    target_id: Snowflake
    value: str

    @property
    def token(self) -> str:
        return f"{self.kind}:{self.id}:{self.revision}"

    @property
    def allocation(self) -> dict[str, int]:
        return (
            {role: self.target_id if role == self.value else self.source_id for role in AM_ROLES}
            if self.kind == "court"
            else {}
        )
