"""Persistent draft input only; no claim of validated official character creation."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from girlframe.engine.playbooks import canonical_frame, canonical_girl


class DraftInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    callsign: str = Field(min_length=1, max_length=32)
    girl_playbook: str = Field(min_length=1, max_length=60)
    frame_playbook: str = Field(min_length=1, max_length=60)
    notes: str = Field(default="", max_length=1000)

    @field_validator("callsign", "girl_playbook", "frame_playbook")
    @classmethod
    def clean_label(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Use a nonempty single-line label")
        return value

    @field_validator("girl_playbook")
    @classmethod
    def known_girl(cls, value: str) -> str:
        return canonical_girl(value)

    @field_validator("frame_playbook")
    @classmethod
    def known_frame(cls, value: str) -> str:
        return canonical_frame(value)
