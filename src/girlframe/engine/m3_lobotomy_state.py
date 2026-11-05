"""Actual experimental surgery selections and original patient's own descriptions."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import ActorRef, Model

Option = Literal["memories", "play", "name", "bonds", "memory"]
OPTIONS: tuple[Option, ...] = ("memories", "play", "name", "bonds", "memory")
PROMPTS = {
    "memories": "Describe your breathing",
    "play": "Describe your eyes as the tools approach",
    "name": "Describe the sound your skull makes",
    "bonds": "Describe your tears",
    "memory": "Describe your expression as the tools leave",
}


class BlockedPlay(Model):
    play: str = Field(min_length=1, max_length=180)
    surgery: str = Field(min_length=1)
    source_event: str = Field(min_length=1)


class Plan(Model):
    options: tuple[Option, ...] = Field(min_length=1, max_length=3)
    room: str = Field(min_length=1, max_length=1200)
    restraints: str = Field(min_length=1, max_length=1200)
    tools: str = Field(min_length=1, max_length=1200)
    erase_slots: tuple[int, ...] = ()
    forbidden_play: str | None = None
    new_name: str = Field(default="", max_length=32)
    inflictor_depth: Literal[0, 1, 2] = 0
    other: ActorRef | None = None
    other_depth: Literal[0, 1, 2] = 0
    memory: str = Field(default="", max_length=1200)
    identity: str = Field(default="", max_length=120)
    replace_identity: str | None = None

    @model_validator(mode="after")
    def exact_choices(self) -> "Plan":
        if len(set(self.options)) != len(self.options) or not all(
            x.strip() for x in (self.room, self.restraints, self.tools)
        ):
            raise ValueError("Describe the actual surgery and choose one to three distinct effects")
        if "memories" in self.options:
            if len(set(self.erase_slots)) != 2 or any(x not in range(4) for x in self.erase_slots):
                raise ValueError("Erase exactly two distinct starting Identity slots")
        elif self.erase_slots:
            raise ValueError("Identity erasure requires the memory-removal effect")
        if ("play" in self.options) != bool(self.forbidden_play):
            raise ValueError("Choose exactly one actual rolled Play for ability removal")
        if "name" not in self.options and self.new_name:
            raise ValueError("Renaming requires actual name removal")
        if any(ord(x) < 32 or ord(x) == 127 for x in self.new_name):
            raise ValueError("A replacement name is a bounded single-line label")
        if "bonds" not in self.options and (self.inflictor_depth or self.other or self.other_depth):
            raise ValueError("New Bonds require actual Bond removal")
        if (self.other is None) != (self.other_depth == 0):
            raise ValueError("An optional other Bond needs its actual character and depth")
        if "memory" in self.options:
            if not self.memory.strip() or not self.identity.strip():
                raise ValueError("Describe the implanted memory and its new Identity")
        elif self.memory or self.identity or self.replace_identity:
            raise ValueError("Implanted Identity details require memory implantation")
        return self


class Response(Model):
    option: Option
    actor: ActorRef
    description: str = Field(min_length=1, max_length=1200)
    source_event: str = Field(min_length=1)


class Surgery(Model):
    id: str = Field(min_length=1)
    subject: ActorRef
    inflictor: ActorRef
    work_ids: tuple[str, ...] = Field(min_length=1)
    source_event: str = Field(min_length=1)
    phase: Literal["plan", "responses", "ready", "applied"] = "plan"
    plan: Plan | None = None
    plan_event: str | None = None
    responses: tuple[Response, ...] = ()
    applied_event: str | None = None

    @model_validator(mode="after")
    def source_owned(self) -> "Surgery":
        if self.subject.kind != "pilot" or self.inflictor.kind != "handler":
            raise ValueError("Severe surgery needs the actual Girl and appointed Handler")
        if self.phase != "plan" and (self.plan is None or self.plan_event is None):
            raise ValueError("Experimental surgery needs the actual inflictor's selections")
        if self.phase in ("ready", "applied") and (
            self.plan is None or {x.option for x in self.responses} != set(self.plan.options)
        ):
            raise ValueError("Each printed description belongs to the actual original patient")
        if len({x.option for x in self.responses}) != len(self.responses) or any(
            x.actor != self.subject or not x.description.strip() for x in self.responses
        ):
            raise ValueError("Do not manufacture or duplicate the original patient's descriptions")
        return self
