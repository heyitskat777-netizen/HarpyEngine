"""Actual fictional Director calls that change or trigger Strain."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine import m3_strain as strain
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_custom_strain import Design, Slot
from girlframe.engine.m3_strain_state import Request, Severity, Track

RULE = "director.director.strain-phone-calls"
PAGE = 192
DIRECT_EVENTS = frozenset(
    {
        "strain.void.low.1.1",
        "strain.void.low.2.1",
        "strain.rebellion.low.1.1",
        "strain.rebellion.low.1.2",
        "strain.budget.low.5.2",
        "strain.budget.high.2.1",
    }
)


class Command(Model):
    mode: Literal["severity", "trigger", "replace"]
    track: Track
    severity: Severity
    slot: Slot | None = None
    design: Design | None = Field(default=None, exclude_if=lambda value: value is None)
    account: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def actual_authority(self) -> "Command":
        if (
            (self.mode in ("trigger", "replace")) != (self.slot is not None)
            or (self.mode == "replace") != (self.design is not None)
            or self.slot is not None
            and (self.slot.track != self.track or self.slot.severity != self.severity)
            or not self.account.strip()
        ):
            raise ValueError("Record one actual phone power and its exact scope")
        return self

    @property
    def target_rule(self) -> str | None:
        if self.slot is None:
            return None
        return f"strain.{self.track}.{self.severity}.{self.slot.face}.{self.slot.column}"


class Call(Model):
    id: str
    sender: ActorRef
    controller: int
    handler: ActorRef
    scene: str
    channel: int
    command: Command
    period: str | None = None
    effect: str | None = None


def calls(state: GameState) -> tuple[Call, ...]:
    return tuple(
        Call.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "director_strain_phone"
    )


def save(state: GameState, call: Call) -> None:
    state.facts.append(dict(kind="director_strain_phone", id=call.id, body=call.model_dump_json()))


def set_level(state: GameState, track: Track, level: Severity) -> tuple[Request, ...]:
    current = state.strain
    if current is None:
        raise ValueError("Initialize the actual Strain tracks before a Director call")
    requested = strain.copy(current, levels={**current.levels, track: level})
    effective = strain.effective_levels(requested)[track]
    changed = tuple(
        x.model_copy(update={"severity": effective})
        for x in current.requests
        if x.kind == "roll" and x.track == track and x.parent is None and x.severity != effective
    )
    changed_by_id = {x.id: x for x in changed}
    state.strain = strain.copy(
        requested, requests=tuple(changed_by_id.get(x.id, x) for x in current.requests)
    )
    return changed
