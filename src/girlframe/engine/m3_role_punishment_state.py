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
    source_kind: Literal[
        "enforcement_initiative",
        "obedience_volunteer",
        "handler_play",
        "compliance_virus",
        "janus_training",
        "alpha_sex",
        "dose_up",
        "vatgrown_doll",
        "show_dog",
        "succubus_npc_disobey",
    ]
    action: str | None = None
    source_work: str | None = None
    source_event: str = Field(min_length=1)
    chooser: ActorRef | None
    chooser_controller: int = Field(gt=0)
    executor: ActorRef
    executor_controller: int = Field(gt=0)
    executor_frame: str | None = Field(default=None, min_length=1)
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
    ended_event: str | None = Field(default=None, exclude_if=lambda value: value is None)
    ended_actor: ActorRef | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def actual_owners(self) -> "RolePunishment":
        if (self.ended_event is None) != (self.ended_actor is None):
            raise ValueError("An impossible original case needs its actual ending actor and source")
        if self.ended_event is not None and (
            self.source_kind != "compliance_virus"
            or self.effect_event is not None
            or self.completion_event is not None
        ):
            raise ValueError(
                "Only an unperformed Virus consequence ends without a fabricated effect"
            )
        if self.source_kind == "succubus_npc_disobey" and (
            self.executor.kind != "handler"
            or self.subject.kind != "npc"
            or self.chooser != self.executor
            or self.action is None
        ):
            raise ValueError("Preserve the actual NPC refusal and original Handler execution")
        if self.source_kind == "show_dog" and (
            self.executor.kind != "handler"
            or self.chooser != self.executor
            or self.source_work is None
            or self.action is None
        ):
            raise ValueError("Preserve Show Dog's actual original Handler and duty source")
        if self.source_kind == "vatgrown_doll" and self.executor.kind not in ("pilot", "handler"):
            raise ValueError("Use this actual Doll source's supported original executor")
        if self.executor.kind not in ("pilot", "npc", "handler", "external_pilot"):
            raise ValueError("Use an actual source-proved executor")
        if self.executor.kind == "external_pilot" and self.source_kind not in (
            "enforcement_initiative",
            "compliance_virus",
        ):
            raise ValueError("Use the actual retained Harpy Initiative or Virus source")
        if self.executor == self.subject and self.source_kind != "compliance_virus":
            raise ValueError("Only an actual Compliance Virus self-purge requires self-Punishment")
        if self.source_kind not in (
            "handler_play",
            "compliance_virus",
            "janus_training",
            "succubus_npc_disobey",
            "vatgrown_doll",
            "show_dog",
        ) and (self.executor.kind not in ("pilot", "external_pilot") or self.chooser is None):
            raise ValueError("Preserve the Enforcer source's original chooser and executor")
        if self.executor.kind in ("pilot", "external_pilot") and self.executor_frame is None:
            raise ValueError("A Girl/Harpy executor preserves its actual source Frame")
        if self.source_kind == "compliance_virus" and (not self.source_work or self.action):
            raise ValueError("Virus uses its real purge work, without a synthetic rolled action")
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
