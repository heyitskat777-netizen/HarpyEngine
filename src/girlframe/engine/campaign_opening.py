"""Group-approved campaign settings and the fictional introductory interval."""

from typing import Literal

from pydantic import Field

from girlframe.engine.identity import Snowflake
from girlframe.engine.m2 import Model

Difficulty = Literal["narrative", "normal", "hard"]
DIFFICULTIES: tuple[Difficulty, ...] = ("narrative", "normal", "hard")
DEFAULT_DIFFICULTY: Difficulty = "normal"
RESTRICTED_PUNISHMENTS = frozenset({"execution", "lobotomization", "indefinite_imprisonment"})
DIFFICULTY_DESCRIPTIONS: dict[Difficulty, str] = {
    "narrative": "Allow up to one player-character death. Restrict the most severe punishments.",
    "normal": "Use the existing GIRL FRAME rules and campaign rulings.",
    "hard": "Use the normal rules and brief an extra obstacle for later missions.",
}


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
