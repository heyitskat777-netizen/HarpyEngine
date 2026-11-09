"""Actual learned AM no-roll sources, never a substitute Action or circuit body."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

RULE = "girl.am.sex-play"


class Source(Model):
    id: str
    lesson: str
    actor: ActorRef
    target: ActorRef
    controllers: dict[str, int]
    vessels: dict[str, str]
    positions: dict[str, str]
    cast: SceneCast
    registry: str
    event: str
    account: str = Field(min_length=1, max_length=1200)
    mode: Literal["both_am", "counterpart"]
    kind: Literal["sex"] = "sex"
    action: None = None
    phase: Literal["invited", "active", "effects", "complete", "declined", "withdrawn"] = "invited"
    consent_event: str | None = None
    counterpart_action: str | None = None
    bound_event: str | None = None
    used_event: str | None = None
    effect_event: str | None = None
    completed_event: str | None = None
    withdrawn_event: str | None = None
    withdrawn_by: ActorRef | None = None
    withdrawal_account: str = ""


class Consent(Model):
    id: str
    source: str
    actor: ActorRef
    controller: int
    accepted: bool
    account: str = Field(min_length=1, max_length=1200)
    event: str


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
        if x.get("kind") == "learned_am_source"
    )


def performances(state: GameState) -> tuple[Performance, ...]:
    return tuple(
        Performance.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "learned_am_performance"
    )


def consents(state: GameState) -> tuple[Consent, ...]:
    return tuple(
        Consent.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "learned_am_consent"
    )


def source(state: GameState, identity: str) -> Source:
    found = [x for x in sources(state) if x.id == identity]
    if len(found) != 1:
        raise ValueError("Recover the actual original learned AM source")
    return found[0]


def put(state: GameState, value: Source | Consent | Performance) -> None:
    kind = (
        "learned_am_source"
        if isinstance(value, Source)
        else "learned_am_consent"
        if isinstance(value, Consent)
        else "learned_am_performance"
    )
    if not isinstance(value, Source) and any(
        x.get("kind") == kind and x.get("id") == value.id for x in state.facts
    ):
        raise ValueError("Preserve each original person's actual response/performance once")
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))
