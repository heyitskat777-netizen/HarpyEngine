"""Actual Foundation rank and original accusations, independent of map guesses."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_world_state import Cell


class RankFact(Model):
    id: str = Field(min_length=1)
    subject: ActorRef
    relative_to: ActorRef
    superior_officer: bool
    handler: ActorRef
    source_event: str = Field(min_length=1)
    account: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def actual_people(self) -> "RankFact":
        if (
            self.subject.kind != "npc"
            or self.relative_to.kind != "pilot"
            or self.handler.kind != "handler"
            or not self.account.strip()
        ):
            raise ValueError("Rank facts name the actual NPC, Girl and adjudicating Handler")
        return self


class Accusation(Model):
    id: str = Field(min_length=1)
    actor: ActorRef
    frame_instance: str = Field(min_length=1)
    subject: ActorRef
    rank_fact: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    account: str = Field(min_length=1, max_length=1200)
    original_cell: Cell
    detained: bool = True
    release_event: str | None = None
    released_by: ActorRef | None = None
    innocence_evidence: str = Field(default="", max_length=1200)
    release_cell: Cell | None = None
    position_event: str | None = None
    position_account: str = Field(default="", max_length=1200)

    @model_validator(mode="after")
    def actual_confinement(self) -> "Accusation":
        if self.actor.kind != "pilot" or self.subject.kind != "npc" or not self.account.strip():
            raise ValueError("An original Enforcer accusation names an actual NPC")
        if self.detained == (self.release_event is not None):
            raise ValueError("Actual detention ends only with its source-proved release")
        if (self.release_event is None) != (self.released_by is None):
            raise ValueError("Release records the actual decision owner")
        if self.released_by is not None and (
            self.released_by.kind != "handler" or not self.innocence_evidence.strip()
        ):
            raise ValueError("The Handler records actual evidence of innocence before release")
        if (self.release_cell is None) != (self.position_event is None):
            raise ValueError("A released NPC's actual location needs its own factual source")
        if self.position_event is not None and (self.detained or not self.position_account.strip()):
            raise ValueError("Record a new actual physical fact only after sourceful release")
        return self


class Grasp(Model):
    id: str = Field(min_length=1)
    actor: ActorRef
    target: ActorRef
    frame_instance: str = Field(min_length=1)
    action: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    contact: Literal["body", "frame"] = "body"
    held: bool = True
    release_event: str | None = None
    release_account: str = Field(default="", max_length=1200)

    @model_validator(mode="after")
    def actual_grip(self) -> "Grasp":
        if self.actor.kind != "pilot" or self.actor == self.target:
            raise ValueError("An actual Enforcer takes hold of another original person")
        if self.held == (self.release_event is not None):
            raise ValueError("The actual grasp has one sourceful owned ending")
        if not self.held and not self.release_account.strip():
            raise ValueError("Describe the actual ending of the grasp")
        return self
