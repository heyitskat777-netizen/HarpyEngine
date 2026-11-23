"""Human-authored Session Zero proposals and character-sheet references."""

from typing import Annotated, Literal

from pydantic import AfterValidator, Field

from girlframe.engine.campaign_opening import (
    DEFAULT_DIFFICULTY,
    CampaignSeats,
    Difficulty,
    HandlerControl,
)
from girlframe.engine.identity import Snowflake
from girlframe.engine.m2 import Model
from girlframe.engine.m3_handler_state import Playbook

MAX_GROUP = 15


def nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("Enter a description.")
    return value.strip()


Name = Annotated[str, Field(max_length=100), AfterValidator(nonblank)]
Description = Annotated[str, Field(max_length=400), AfterValidator(nonblank)]


class HandlerProfile(Model):
    member: Snowflake
    player_name: Name | None = None
    name: Name
    archetype: Playbook
    appearance: Description
    personality: Description
    control: HandlerControl = Field(default="player", exclude_if=lambda x: x == "player")


class CharacterNotes(Model):
    goal: str = Field(default="", max_length=400)
    hook: str = Field(default="", max_length=400)
    spotlight: str = Field(default="", max_length=400)


class SheetReference(Model):
    kind: Literal["active", "saved_review"]
    character: str
    version: str
    callsign: str
    girl: str
    frame: str


class CharacterSubmission(Model):
    sheet: SheetReference
    notes: CharacterNotes = Field(default_factory=CharacterNotes)


class SessionZero(Model):
    revision: int = 0
    members: tuple[Snowflake, ...] = ()
    proposal: str | None = None
    handler: HandlerProfile | None = None
    approvals: tuple[Snowflake, ...] = ()
    submissions: dict[str, CharacterSubmission] = Field(default_factory=dict)
    goals: str = Field(default="", max_length=800)
    difficulty: Difficulty = DEFAULT_DIFFICULTY
    plan_proposal: str | None = None
    plan_approvals: tuple[Snowflake, ...] = ()
    seats: CampaignSeats | None = Field(default=None, exclude_if=lambda x: x is None)
    facilitator: Snowflake | None = Field(default=None, exclude_if=lambda x: x is None)
    facilitator_only: bool = Field(default=False, exclude_if=lambda x: not x)

    @property
    def plan_approved(self) -> bool:
        return self.plan_proposal is not None and set(self.members) == set(self.plan_approvals)

    @property
    def approved(self) -> bool:
        return self.handler is not None and set(self.members) == set(self.approvals)

    @property
    def pilots(self) -> tuple[Snowflake, ...]:
        return tuple(
            uid
            for uid in self.members
            if (self.handler is None or uid != self.handler.member)
            and (not self.facilitator_only or uid != self.facilitator)
        )

    @property
    def human_players(self) -> int:
        return len(self.pilots) + int(self.handler is not None and self.handler.control == "player")
