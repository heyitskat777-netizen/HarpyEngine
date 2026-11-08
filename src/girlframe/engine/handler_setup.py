"""Draft Handler assignments; no game effects, private notes or Discord permissions."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from girlframe.engine.creation_review import CreationRulings
from girlframe.engine.identity import Snowflake


class PilotRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    user_id: Snowflake
    character_revision: int = Field(ge=1)


class MentorAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    assignment_id: str
    newgirl: PilotRef
    mentor: PilotRef


class HandlerSetup(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    handler_id: Snowflake | None = None
    mentors: tuple[MentorAssignment, ...] = ()
    status_order: tuple[PilotRef, ...] = ()
    creation_rulings: CreationRulings | None = None
    creation_rulings_explicit: bool = False

    @model_validator(mode="after")
    def distinct_roles(self) -> Self:
        if len({x.user_id for x in self.status_order}) != len(self.status_order):
            raise ValueError("A Pilot can hold only one position")
        if len({x.newgirl.user_id for x in self.mentors}) != len(self.mentors):
            raise ValueError("A starting Newgirl can have only one current nomination")
        if any(
            x.newgirl.user_id == x.mentor.user_id
            or self.handler_id in (x.newgirl.user_id, x.mentor.user_id)
            for x in self.mentors
        ):
            raise ValueError("Mentor roles require two distinct Pilots")
        if self.handler_id in {x.user_id for x in self.status_order}:
            raise ValueError("Handler is outside Pilot ranks")
        return self
