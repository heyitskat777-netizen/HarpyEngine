"""One actual OOC session and source-backed starting-Identity advancement criterion."""

from typing import Final, Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model

RULE: Final = "source.handler-advancement-triggers"


class Session(Model):
    id: str
    facilitator: int
    appointment: str
    name: str = Field(min_length=1, max_length=120)
    start_event: str
    started_at: str
    account: str = Field(min_length=1, max_length=1200)
    end_event: str | None = None
    ended_at: str | None = None
    end_account: str | None = None


class Edge(Model):
    old: str
    new: str
    name: str
    event: str
    choice: str
    action: str


class Chain(Model):
    starting: str
    current: str
    name: str
    edges: tuple[Edge, ...]


class Evidence(Model):
    actor: ActorRef
    activation: str
    chains: tuple[Chain, ...]


class Review(Model):
    id: str
    session: str
    handler: ActorRef
    appointment: str
    evidence: Evidence
    request_event: str
    account: str = Field(min_length=1, max_length=1200)
    phase: Literal["disclosure", "usefulness", "declined", "awarded"] = "disclosure"
    decision_event: str | None = None
    decision_account: str | None = None
    judgment_event: str | None = None
    judgment_session: str | None = None
    reasons: dict[str, str] = Field(default_factory=dict)
    award: str | None = None


class AwardSource(Model):
    session: str
    review: str
    trigger: Literal["identities_useful", "public_relations"] = "identities_useful"


class Mark(Model):
    id: str
    handler: ActorRef
    session: str
    review: str
    award: str
    event: str
    trigger: Literal["identities_useful", "public_relations"] = "identities_useful"


def sessions(state: GameState) -> tuple[Session, ...]:
    return tuple(
        Session.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "handler_campaign_session"
    )


def reviews(state: GameState) -> tuple[Review, ...]:
    return tuple(
        Review.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "handler_identity_review"
    )


def marks(state: GameState) -> tuple[Mark, ...]:
    return tuple(
        Mark.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "handler_ordinary_mark"
    )


def put(state: GameState, value: Session | Review | Mark) -> None:
    kind = (
        "handler_campaign_session"
        if isinstance(value, Session)
        else "handler_identity_review"
        if isinstance(value, Review)
        else "handler_ordinary_mark"
    )
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))
