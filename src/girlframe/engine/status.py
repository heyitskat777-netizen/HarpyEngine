"""Minimal status projection. No mechanics, identity, or private world facts."""

from pydantic import BaseModel, ConfigDict, Field


class PublicCampaignStatus(BaseModel):
    """Candidate public fields; a GM must approve their audience before Discord use."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    turn: int = Field(ge=0)
    paused: bool
