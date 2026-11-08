"""Actual spinal contact and source-bound control, separate from cockpit occupancy."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast


class NeuralConnection(Model):
    id: str = Field(min_length=1)
    caster: ActorRef
    caster_controller: int = Field(gt=0)
    battery: ActorRef
    battery_controller: int = Field(gt=0)
    frame_owner: ActorRef
    frame_instance: str = Field(min_length=1)
    cast: SceneCast
    judge: int = Field(gt=0)
    judge_actor: ActorRef | None = None
    appointment: str = Field(min_length=1)
    proposed_event: str = Field(min_length=1)
    account: str = Field(min_length=1, max_length=1200)
    access: Literal["core_port", "consensual", "source_force"]
    access_source: str = Field(min_length=1)
    port_access: Literal["exposed_spine", "own_cockpit", "reviewed_port"]
    port_source: str = Field(min_length=1)
    phase: Literal["target", "review", "connected", "refused", "unplugged", "ended"]
    target_event: str | None = None
    review_event: str | None = None
    review: str = Field(default="", max_length=1200)
    connected_event: str | None = None
    ended_event: str | None = None
    ended_by: ActorRef | None = None
    end_account: str = Field(default="", max_length=1200)

    @model_validator(mode="after")
    def actual(self) -> "NeuralConnection":
        if self.caster == self.battery:
            raise ValueError("An actual spinal connection has two distinct original bodies")
        if self.phase == "connected" and self.connected_event is None:
            raise ValueError("Actual contact needs its reviewed performed source event")
        if self.phase in ("unplugged", "ended") and self.ended_event is None:
            raise ValueError("Actual unplug or interruption retains its own source")
        if self.access == "consensual" and self.connected_event and self.target_event is None:
            raise ValueError("Optional spinal contact retains the actual other body's response")
        return self


class FrameCommand(Model):
    id: str = Field(min_length=1)
    actor: ActorRef
    frame_owner: ActorRef
    frame_instance: str = Field(min_length=1)
    connection: str = Field(min_length=1)
    battery_link: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    active: bool = True
    ended_event: str | None = None
    recovered_event: str | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def actual(self) -> "FrameCommand":
        if self.active == (self.ended_event is not None):
            raise ValueError("Actual finite Frame control needs its real ending event")
        return self
