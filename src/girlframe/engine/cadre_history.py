"""Newgirl's player-authored prior-mission declarations, book PDF 40."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from girlframe.engine.identity import Snowflake


class PriorMission(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    user_id: Snowflake
    character_revision: int | None = Field(default=None, ge=1)
    missions: Literal[0, 1]
