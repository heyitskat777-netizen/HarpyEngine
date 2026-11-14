"""Actual AM no-roll sources, never a substitute Action or circuit body."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

RULE = "girl.am.sex-play"


class Source(Model):
    id: str
    lesson: str | None = Field(default=None, exclude_if=lambda value: value is None)
    native: Literal[True] | None = Field(default=None, exclude_if=lambda value: value is None)
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

    @model_validator(mode="after")
    def actual_entitlement(self) -> "Source":
        if bool(self.native) != (self.lesson is None) or self.native and self.mode != "both_am":
            raise ValueError(
                "Keep actual native AM ownership separate from one real learned lesson"
            )
        return self


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
    result = []
    for fact in state.facts:
        if fact.get("kind") not in ("learned_am_source", "native_am_source"):
            continue
        value = Source.model_validate_json(fact["body"])
        if bool(value.native) != (fact["kind"] == "native_am_source"):
            raise ValueError("Preserve the actual AM source's entitlement namespace")
        result.append(value)
    return tuple(result)


def performances(state: GameState) -> tuple[Performance, ...]:
    result = []
    for fact in state.facts:
        if fact.get("kind") not in ("learned_am_performance", "native_am_performance"):
            continue
        value = Performance.model_validate_json(fact["body"])
        if bool(source(state, value.source).native) != (fact["kind"] == "native_am_performance"):
            raise ValueError("Preserve the actual performance's original source namespace")
        result.append(value)
    return tuple(result)


def consents(state: GameState) -> tuple[Consent, ...]:
    result = []
    for fact in state.facts:
        if fact.get("kind") not in ("learned_am_consent", "native_am_consent"):
            continue
        value = Consent.model_validate_json(fact["body"])
        if bool(source(state, value.source).native) != (fact["kind"] == "native_am_consent"):
            raise ValueError("Preserve the actual consent's original source namespace")
        result.append(value)
    return tuple(result)


def source(state: GameState, identity: str) -> Source:
    found = [x for x in sources(state) if x.id == identity]
    if len(found) != 1:
        raise ValueError("Recover the actual original learned AM source")
    return found[0]


def put(state: GameState, value: Source | Consent | Performance) -> None:
    suffix = (
        "source"
        if isinstance(value, Source)
        else "consent"
        if isinstance(value, Consent)
        else "performance"
    )
    actual = value if isinstance(value, Source) else source(state, value.source)
    kind = ("native_am_" if actual.native else "learned_am_") + suffix
    if not isinstance(value, Source) and any(
        x.get("kind") == kind and x.get("id") == value.id for x in state.facts
    ):
        raise ValueError("Preserve each original person's actual response/performance once")
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))
