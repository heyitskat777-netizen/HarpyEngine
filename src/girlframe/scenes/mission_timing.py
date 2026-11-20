"""Fictional minute inputs and the bounded mission-clock state."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from girlframe.engine.m2 import Model
from girlframe.scenes.campaign_time import Account, Identity, Principal

Minute = Annotated[int, Field(ge=0, lt=1440)]
Duration = Annotated[int, Field(ge=1, lt=1440)]
Boundary = Literal["before", "by"]
DeadlineStatus = Literal["open", "at_deadline", "missed"]


class Deadline(Model):
    minute: Minute
    boundary: Boundary
    label: Account
    consequence: Account | None = None

    def status(self, minute: int) -> DeadlineStatus:
        if minute > self.minute or (minute == self.minute and self.boundary == "before"):
            return "missed"
        return "at_deadline" if minute == self.minute else "open"


class SequenceStart(Model):
    minute: Minute
    deadline: Deadline

    @model_validator(mode="after")
    def before_deadline(self) -> Self:
        if self.minute >= self.deadline.minute:
            raise ValueError("Start before the deadline on the same fictional day.")
        return self


class Option(Model):
    id: Identity
    pilot: Principal
    label: Account
    minutes: Duration | None = None
    estimated: bool = False
    play: Literal["keep_your_head"] | None = None

    @model_validator(mode="after")
    def known_estimate(self) -> Self:
        if self.estimated and self.minutes is None:
            raise ValueError("An estimated option needs a stated minute cost.")
        return self


class Options(Model):
    mode: Literal["single", "parallel"] = "single"
    available: Annotated[tuple[Option, ...], Field(min_length=1, max_length=25)]

    @model_validator(mode="after")
    def distinct(self) -> Self:
        if len({item.id for item in self.available}) != len(self.available):
            raise ValueError("Give each option a distinct identity.")
        pilots = {item.pilot for item in self.available}
        if self.mode == "single" and len(pilots) != 1:
            raise ValueError("A single exchange belongs to one Pilot.")
        if self.mode == "parallel" and (
            len(pilots) < 2 or any(item.play or item.minutes is None for item in self.available)
        ):
            raise ValueError(
                "Parallel exchanges require stated costs and direct options for distinct Pilots."
            )
        return self


class Selected(Model):
    receipt: Identity
    option: Option


class Rejoin(Model):
    minute: Minute
    account: Account


class Ruling(Model):
    reason: Literal["unknown_duration", "unknown_consequence"]
    option: Identity | None = None
    pilot: Principal | None = None
    proposed_rejoin: Rejoin | None = None


class Clock(Model):
    id: Identity
    mission: Identity
    scene: Identity
    channel: Principal
    anchor: Identity
    day: int
    minute: Minute
    deadline: Deadline
    closed: bool = False
    consequence_receipt: Identity | None = None
    menu_receipt: Identity | None = None
    menu: Options | None = None
    selected: tuple[Selected, ...] = ()
    ruling: Ruling | None = None
