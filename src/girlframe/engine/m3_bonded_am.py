"""Actual Bonded/AM no-roll performances, distinct from any borrowed body or circuits."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

RULE = "girl.am.sex-play"


class Source(Model):
    id: str
    bonded_source: str
    actor: ActorRef
    target: ActorRef
    controllers: dict[str, int]
    vessels: dict[str, str]
    positions: dict[str, str]
    cast: SceneCast
    registry: str
    event: str
    account: str = Field(min_length=1, max_length=1200)
    kind: Literal["sex"] = "sex"
    action: None = None
    phase: Literal["active", "effects", "complete", "withdrawn"] = "active"
    effect_event: str | None = None
    completed_event: str | None = None
    withdrawn_event: str | None = None
    withdrawn_by: ActorRef | None = None
    withdrawal_account: str = ""


class Performance(Model):
    id: str
    source: str
    actor: ActorRef
    controller: int
    account: str = Field(min_length=1, max_length=1200)
    circuits_touched: Literal[False] = False
    event: str


def sources(state: GameState) -> tuple[Source, ...]:
    return tuple(
        Source.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "bonded_am_source"
    )


def performances(state: GameState) -> tuple[Performance, ...]:
    return tuple(
        Performance.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "bonded_am_performance"
    )


def source(state: GameState, identity: str) -> Source:
    value = next((x for x in sources(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Recover the actual original Bonded/AM performed source")
    return value


def put(state: GameState, value: Source | Performance) -> None:
    kind = "bonded_am_source" if isinstance(value, Source) else "bonded_am_performance"
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == value.id)
    ] + [dict(kind=kind, id=value.id, body=value.model_dump_json())]
