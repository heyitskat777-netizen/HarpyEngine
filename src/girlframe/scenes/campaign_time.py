"""Typed fictional calendar inputs for the offline campaign-time slice."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AfterValidator, Field, model_validator

from girlframe.engine.m2 import Model

Slot = Literal["morning", "afternoon", "night"]
SLOTS: tuple[Slot, ...] = ("morning", "afternoon", "night")
Principal = Annotated[int, Field(gt=0, lt=2**64)]


def nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("Enter a nonempty value.")
    return value.strip()


def identity(value: str) -> str:
    return str(UUID(value))


Identity = Annotated[str, AfterValidator(identity)]
Chapter = Annotated[str, Field(max_length=100), AfterValidator(nonblank)]
Account = Annotated[str, Field(max_length=1200), AfterValidator(nonblank)]


class Position(Model):
    day: Annotated[int, Field(gt=0, le=999_999)]
    slot: Slot

    @property
    def order(self) -> tuple[int, int]:
        return self.day, SLOTS.index(self.slot)


class Anchor(Model):
    chapter: Chapter
    position: Position


class ScenePlan(Model):
    chapter: Chapter | None = None
    start: Position
    end: Position
    participants: Annotated[tuple[Principal, ...], Field(min_length=1, max_length=32)]
    allow_late_narration: bool = False
    narrative_only: bool = Field(default=False, exclude_if=lambda value: not value)

    @model_validator(mode="after")
    def validate_booking(self) -> Self:
        if self.start.order > self.end.order:
            raise ValueError("A scene span must end at or after its opening slot.")
        if len(set(self.participants)) != len(self.participants):
            raise ValueError("List each scheduled participant once.")
        return self

    def overlaps(self, other: Self) -> bool:
        return self.start.order <= other.end.order and other.start.order <= self.end.order


class Dependency(Model):
    kind: Literal["work", "choice", "play_receipt"]
    id: Identity


class Cut(Model):
    target: Anchor
    requires: Annotated[tuple[Dependency, ...], Field(max_length=20)] = ()

    @model_validator(mode="after")
    def unique_dependencies(self) -> Self:
        if len({(x.kind, x.id) for x in self.requires}) != len(self.requires):
            raise ValueError("List each required outcome once.")
        return self


class LateSubmission(Model):
    kind: Literal["narration", "knowledge", "mechanical", "uncertain"]
    account: Account
    recipients: Annotated[tuple[Principal, ...], Field(max_length=32)] = ()

    @model_validator(mode="after")
    def validate_audience(self) -> Self:
        if (self.kind == "knowledge") != bool(self.recipients):
            raise ValueError("Name specific recipients for a knowledge record.")
        if len(set(self.recipients)) != len(self.recipients):
            raise ValueError("Name each recipient once.")
        return self
