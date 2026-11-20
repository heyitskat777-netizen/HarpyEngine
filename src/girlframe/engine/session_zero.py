"""Human-authored Session Zero proposals and character-sheet references."""

from typing import Annotated, Literal

from pydantic import AfterValidator, Field

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

    @property
    def approved(self) -> bool:
        return self.handler is not None and set(self.members) == set(self.approvals)

    @property
    def pilots(self) -> tuple[Snowflake, ...]:
        return tuple(
            uid for uid in self.members if self.handler is None or uid != self.handler.member
        )
