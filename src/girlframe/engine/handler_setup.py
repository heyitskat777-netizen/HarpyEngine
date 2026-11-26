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
    late_wings: tuple[PilotRef, ...] = ()
    creation_rulings: CreationRulings | None = None
    creation_rulings_explicit: bool = False
    starting_bond_test_bypasses: tuple[PilotRef, ...] = ()

    @model_validator(mode="after")
    def distinct_roles(self) -> Self:
        if len({x.user_id for x in self.starting_bond_test_bypasses}) != len(
            self.starting_bond_test_bypasses
        ):
            raise ValueError("Only one starting-Bond test bypass per Pilot")
        if len({x.user_id for x in self.status_order}) != len(self.status_order):
            raise ValueError("A Pilot can hold only one position")
        if len({x.user_id for x in self.late_wings}) != len(self.late_wings):
            raise ValueError("A Pilot can hold only one late enrollment assignment")
        if len({x.newgirl.user_id for x in self.mentors}) != len(self.mentors):
            raise ValueError("A starting Newgirl can have only one current nomination")
        if any(x.newgirl.user_id == x.mentor.user_id for x in self.mentors):
            raise ValueError("Mentor roles require two distinct Pilots")
        return self
