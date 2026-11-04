"""Canonical Strain inventory and stable pending requests; no rules or adapters."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from girlframe.engine.rolls import Face

Track = Literal["void", "rebellion", "budget"]
Severity = Literal["low", "high"]
Scenario = Literal["business_as_usual", "disaster_management", "barely_hanging_on", "falling_apart"]
TRACKS: tuple[Track, ...] = ("void", "rebellion", "budget")


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class PeriodRecord(Model):
    id: str
    period_id: str
    track: Track
    parent: str | None = None


class Request(PeriodRecord):
    kind: Literal["roll", "endgame"] = "roll"
    severity: Severity | None = None

    @model_validator(mode="after")
    def table(self) -> "Request":
        if (self.kind == "roll") != (self.severity is not None):
            raise ValueError("A roll request must specify its actual Strain table")
        if self.kind == "endgame" and self.parent is None:
            raise ValueError("Endgame requests require an actual source event")
        return self


class Event(PeriodRecord):
    severity: Severity
    face: Face
    column: Literal[1, 2] | None = None

    @property
    def rule_id(self) -> str | None:
        if self.column is None:
            return None
        return f"strain.{self.track}.{self.severity}.{self.face}.{self.column}"


class Endgame(PeriodRecord):
    option: int = Field(ge=1, le=8)
    parent: str = Field()

    @property
    def rule_id(self) -> str:
        return f"strain.{self.track}.endgame.{self.option}"


class Trigger(Model):
    id: str
    kind: Literal["structure_destroyed", "girl_death_or_severe"]
    entity: str
    source_event: str
    consumed_by: str | None = None


class State(Model):
    scenario: Scenario
    levels: dict[Track, Severity]
    periods: tuple[str, ...] = ()
    requests: tuple[Request, ...] = ()
    events: tuple[Event, ...] = ()
    endgames: tuple[Endgame, ...] = ()
    repeated: frozenset[Track] = frozenset()
    triggers: tuple[Trigger, ...] = ()

    @model_validator(mode="after")
    def inventory(self) -> "State":
        if set(self.levels) != set(TRACKS) or len(set(self.periods)) != len(self.periods):
            raise ValueError("Retain all three Strain tracks and distinct period starts")
        if len({x.id for x in self.triggers}) != len(self.triggers) or any(
            x.consumed_by is not None and x.consumed_by not in self.periods for x in self.triggers
        ):
            raise ValueError(
                "Canonical Strain triggers need distinct IDs and actual consuming periods"
            )
        ids = [x.id for x in (*self.requests, *self.events, *self.endgames)]
        if len(set(ids)) != len(ids):
            raise ValueError("Strain requests and outcomes must have distinct stable IDs")
        if any(
            x.period_id not in self.periods for x in (*self.requests, *self.events, *self.endgames)
        ):
            raise ValueError("Strain requests require a real recorded period start")
        if len({x.rule_id for x in self.endgames}) != len(self.endgames):
            raise ValueError("An Endgame slot may only be chosen once")
        parents = {x.id: x for x in self.events}
        for entry in (*self.requests, *self.events, *self.endgames):
            if entry.parent is not None:
                parent = parents.get(entry.parent)
                if parent is None or (
                    parent.track != entry.track
                    or parent.period_id != entry.period_id
                    or (parent.severity, parent.face, parent.column) != ("high", 6, 2)
                ):
                    raise ValueError(
                        "Recursive work needs its actual selected same-track source event"
                    )
        if any(x.option > (8 if x.track == "rebellion" else 7) for x in self.endgames):
            raise ValueError("Endgame slot is outside its source table")
        return self
