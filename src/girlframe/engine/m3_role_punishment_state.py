"""Instruction ownership and actual execution remain separate source-bound roles."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import ActorRef, Model


class Instruction(Model):
    kind: str = Field(min_length=1)
    details_json: str = Field(min_length=1)
    counterpart: ActorRef | None = None


class RolePunishment(Model):
    id: str = Field(min_length=1)
    source_kind: Literal["enforcement_initiative", "obedience_volunteer"]
    action: str | None = None
    source_work: str | None = None
    source_event: str = Field(min_length=1)
    chooser: ActorRef
    chooser_controller: int = Field(gt=0)
    executor: ActorRef
    executor_controller: int = Field(gt=0)
    executor_frame: str = Field(min_length=1)
    subject: ActorRef
    subject_controller: int = Field(gt=0)
    instruction: Instruction | None = None
    instruction_event: str | None = None
    handler_approval_event: str | None = None
    handler_approver: ActorRef | None = None
    scene_account: str = Field(default="", max_length=1200)
    attendance: tuple[int, ...] = ()
    pc_work: str | None = None
    effect_event: str | None = None
    execution_account: str = Field(default="", max_length=1200)
    completion_event: str | None = None

    @model_validator(mode="after")
    def actual_owners(self) -> "RolePunishment":
        if self.executor.kind != "pilot" or self.executor == self.subject:
            raise ValueError("An original actual Enforcer carries out another person's Punishment")
        if (self.instruction is None) != (self.instruction_event is None):
            raise ValueError("The actual chooser's exact instruction needs its source")
        if len(set(self.attendance)) != len(self.attendance) or not set(self.attendance) <= {
            self.executor_controller,
            self.subject_controller,
        }:
            raise ValueError("Only actual on-screen participants record their own attendance")
        if self.attendance and not self.scene_account.strip():
            raise ValueError("Describe the actual on-screen Punishment scene")
        if self.completion_event and not self.effect_event:
            raise ValueError(
                "A Punishment completes after a real applied effect and required followups"
            )
        return self
