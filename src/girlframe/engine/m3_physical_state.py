"""Actual original Pilot placement; character identity is not a physical vessel."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.identity import Snowflake
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_world_state import Cell

Mode = Literal["outside_frame", "inside_frame", "piloting"]


class InitialPlacement(Model):
    actor: ActorRef
    frame_instance: str = Field(min_length=1, max_length=180)
    girl_cell: Cell
    frame_cell: Cell
    mode: Mode
    account: str = Field(min_length=1, max_length=1200)
    facts_confirmed: Literal[True]

    @model_validator(mode="after")
    def actual_facts(self) -> "InitialPlacement":
        if self.actor.kind != "pilot" or not self.account.strip():
            raise ValueError("Record the actual original Girl, Frame and physical facts")
        if self.mode != "outside_frame" and self.girl_cell != self.frame_cell:
            raise ValueError("A Girl inside a Frame is at that actual Frame's map cell")
        return self


class Placement(Model):
    actor: ActorRef
    vessel_id: str = Field(min_length=1, max_length=100)
    frame_instance: str = Field(min_length=1, max_length=180)
    girl_cell: Cell
    frame_cell: Cell
    mode: Mode
    proposed_event: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    account: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def actual_placement(self) -> "Placement":
        if self.actor.kind != "pilot" or any(
            not x.strip()
            for x in (
                self.vessel_id,
                self.frame_instance,
                self.proposed_event,
                self.source_event,
                self.account,
            )
        ):
            raise ValueError("An original Pilot placement retains its actual character and source")
        if self.mode != "outside_frame" and self.girl_cell != self.frame_cell:
            raise ValueError("An occupied Frame and its Girl share the actual map cell")
        if self.proposed_event == self.source_event:
            raise ValueError("The owned factual proposal and actual review have distinct events")
        return self


class Review(Model):
    proposal: InitialPlacement
    label: str = Field(min_length=1, max_length=120)
    handler: Snowflake
    proposed_event: str = Field(min_length=1)
    decision: Literal["pending", "accepted", "declined", "withdrawn"] = "pending"
    review_event: str | None = None
    vessel_id: str | None = None
    response: str = Field(default="", max_length=1200)

    @model_validator(mode="after")
    def actual_review(self) -> "Review":
        if self.decision == "pending":
            if self.review_event is not None or self.vessel_id is not None or self.response:
                raise ValueError("A pending physical proposal has no invented review")
        elif (
            not self.review_event
            or not self.response.strip()
            or self.review_event == self.proposed_event
        ):
            raise ValueError("Record the actual distinct owned review source and response")
        if (self.decision == "accepted") != (self.vessel_id is not None):
            raise ValueError("Only accepted original physical facts establish a vessel")
        return self
