"""Factual original external poses and actual source-bound influence-trail arrivals."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_world_state import Cell


class ExternalPose(Model):
    actor: ActorRef
    vessel: str = Field(min_length=1)
    frame: str = Field(min_length=1)
    girl_cell: Cell | None
    frame_cell: Cell | None
    mode: Literal["outside_frame", "inside_frame", "piloting"]
    source_event: str = Field(min_length=1)
    position_event: str = Field(min_length=1)
    owner: int = Field(gt=0)
    judge: int = Field(gt=0)
    account: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def original_external(self) -> "ExternalPose":
        if self.actor.kind != "external_pilot" or (
            self.mode != "outside_frame" and self.girl_cell != self.frame_cell
        ):
            raise ValueError("Record the original external Girl's actual body and own Frame")
        return self


class LeviathanArrival(Model):
    actor: ActorRef
    source: ActorRef
    mover: ActorRef
    cell: Cell | None
    frame_owner: ActorRef | None = None
    frame: str | None = None
    source_action: str = Field(min_length=1)
    arrival_event: str = Field(min_length=1)
    position_event: str = Field(min_length=1)
    custody: str | None = None
    account: str = Field(min_length=1, max_length=1200)
    already_at_endpoint: bool = False

    @model_validator(mode="after")
    def actual_endpoint(self) -> "LeviathanArrival":
        if (
            self.source.kind != "gorgon"
            or self.actor == self.source
            or ((self.frame_owner is None) != (self.frame is None))
        ):
            raise ValueError("The actual original person reaches this distinct source Leviathan")
        return self


class ArrivalRequirement(Model):
    actor: ActorRef
    source: ActorRef
    mover: ActorRef | None
    frame_owner: ActorRef | None = None
    frame: str | None = None
    destination: Cell | None
    actor_position: str
    source_position: str
    mover_position: str | None = None
    blocker: str | None = None
    method: Literal["self", "carried", "hauled"] = "self"
    attestors: tuple[ActorRef, ...] = ()
