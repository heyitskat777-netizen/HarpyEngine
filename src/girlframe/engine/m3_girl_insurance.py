"""One actual next-death insurance source and its exact consumed Budget effect."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model

RULE = "handler-advancement.handler-advancement.girl-insurance"


class Acquisition(Model):
    id: str
    award: str
    handler: ActorRef
    appointment: str
    event: str
    account: str = Field(min_length=1, max_length=1200)


class Consumption(Model):
    id: str
    acquisition: str
    actor: ActorRef
    archive: str
    event: str
    budget_before: Literal["low", "high"]
    budget_after: Literal["low"] = "low"

    @model_validator(mode="after")
    def original_death(self) -> "Consumption":
        if self.actor.kind != "pilot" or self.id != self.acquisition + ":death":
            raise ValueError("Keep this one actual original Girl's insured death")
        return self


def acquisitions(state: GameState) -> tuple[Acquisition, ...]:
    return tuple(
        Acquisition.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "girl_insurance_acquisition"
    )


def consumptions(state: GameState) -> tuple[Consumption, ...]:
    values = tuple(
        Consumption.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "girl_insurance_consumption"
    )
    if len({x.acquisition for x in values}) != len(values):
        raise ValueError("An actual Girl Insurance acquisition is consumed only once")
    return values


def put(state: GameState, value: Acquisition | Consumption) -> None:
    kind = (
        "girl_insurance_acquisition"
        if isinstance(value, Acquisition)
        else "girl_insurance_consumption"
    )
    if any(x.get("kind") == kind and x.get("id") == value.id for x in state.facts):
        raise ValueError("Keep the immutable original insurance source and single consumption")
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))


def active(state: GameState) -> tuple[Acquisition, ...]:
    spent = {x.acquisition for x in consumptions(state)}
    return tuple(x for x in acquisitions(state) if x.id not in spent)


def budget_death_excluded(state: GameState, event: str, archive_id: str) -> bool:
    return any(
        x.event == event
        and x.archive == archive_id
        and any(
            a.id == archive_id
            and a.actor == x.actor
            and a.source_event == event
            and a.ending in ("death", "execution")
            for a in state.career_archives
        )
        and any(a.id == x.acquisition for a in acquisitions(state))
        for x in consumptions(state)
    )
