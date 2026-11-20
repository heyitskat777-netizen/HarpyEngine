"""Group-approved campaign settings and the fictional introductory interval."""

from typing import Annotated, Literal

from pydantic import AfterValidator, Field, field_validator

from girlframe.engine.identity import Snowflake
from girlframe.engine.m2 import Model

Difficulty = Literal["narrative", "normal", "hard"]
HandlerControl = Literal["player", "ai"]
DIFFICULTIES: tuple[Difficulty, ...] = ("narrative", "normal", "hard")
DEFAULT_DIFFICULTY: Difficulty = "normal"
RESTRICTED_PUNISHMENTS = frozenset({"execution", "lobotomization", "indefinite_imprisonment"})
DIFFICULTY_DESCRIPTIONS: dict[Difficulty, str] = {
    "narrative": "Allow up to one player-character death. Restrict the most severe punishments.",
    "normal": "Use the existing GIRL FRAME rules and campaign rulings.",
    "hard": "Use the normal rules and brief an extra obstacle for later missions.",
}


def _trim_callsign(value: str) -> str:
    if not value.strip():
        raise ValueError("Enter a callsign for each planned AI Pilot.")
    return value.strip()


class PlannedAIPilot(Model):
    callsign: Annotated[str, Field(max_length=100), AfterValidator(_trim_callsign)]
    concept: str = Field(default="", max_length=400)


class CampaignSeats(Model):
    player_count: int = Field(ge=1, le=15)
    ai_pilots: tuple[PlannedAIPilot, ...] = Field(default=(), max_length=15)

    @field_validator("ai_pilots")
    @classmethod
    def distinct_callsigns(cls, pilots: tuple[PlannedAIPilot, ...]) -> tuple[PlannedAIPilot, ...]:
        if len({pilot.callsign.casefold() for pilot in pilots}) != len(pilots):
            raise ValueError("Choose distinct callsigns for the planned AI Pilots.")
        return pilots


class Opening(Model):
    scene: str
    channel: Snowflake
    handler: Snowflake
    audience: tuple[Snowflake, ...]
    plan: str
    goals: str
    difficulty: Difficulty
    introduction: str = Field(min_length=1, max_length=1200)
    first_mission_day: int
    handler_control: HandlerControl | None = Field(default=None, exclude_if=lambda x: x is None)
    seats: CampaignSeats | None = Field(default=None, exclude_if=lambda x: x is None)
