"""Original Princess intimacy and one source-bound counterpart decision directive."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

RULE = "girl.princess.sex-play"
PLAY = "princess_sex"


class Session(Model):
    id: str
    actor: ActorRef
    target: ActorRef
    caster: int
    counterpart: int
    cast: SceneCast
    registry: str
    bonded_source: str | None = Field(default=None, exclude_if=lambda value: value is None)
    changeling_source: str | None = Field(default=None, exclude_if=lambda value: value is None)
    proposed_event: str
    proposal: str = Field(min_length=1, max_length=1200)
    consent_event: str | None = None
    consent_account: str = ""
    phase: Literal[
        "invited",
        "accepted",
        "declined",
        "active",
        "low_tag",
        "favour",
        "favour_reply",
        "optional_tag",
        "direction",
        "child",
        "complete",
    ] = "invited"
    action: str | None = None
    bound_event: str | None = None
    effect_event: str | None = None
    tier: Literal["low", "mid", "high"] | None = None
    favour: str | None = None
    favour_event: str | None = None
    response: Literal["agree", "refuse"] | None = None
    response_account: str | None = None
    response_event: str | None = None
    tag: str | None = None
    tag_event: str | None = None
    bond_before: int | None = None
    bond_after: int | None = None
    direction: str | None = None
    completed_event: str | None = None


class HighDirection(Model):
    id: str
    session: str
    parent: str
    actor: ActorRef
    actor_controller: int
    author: ActorRef
    author_controller: int
    source_event: str
    selected_choice: str
    selected_event: str
    play: Literal[
        "keep_your_head",
        "check_sensors",
        "flirt",
        "engage",
        "all_out_assault",
        "put_someone_beneath_you",
        "disobey_orders",
    ]
    target: ActorRef | None = Field(default=None, exclude_if=lambda value: value is None)
    order_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    context: str = Field(min_length=1, max_length=1200)
    child: str | None = None
    bound_event: str | None = None
    completed_event: str | None = None


def sessions(state: GameState) -> tuple[Session, ...]:
    return tuple(
        Session.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "princess_sex_session"
    )


def directions(state: GameState) -> tuple[HighDirection, ...]:
    return tuple(
        HighDirection.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "princess_sex_direction"
    )


def get(state: GameState, identity: str) -> Session:
    value = next((x for x in sessions(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Recover the real original Princess interaction")
    return value


def direction(state: GameState, identity: str) -> HighDirection:
    value = next((x for x in directions(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Recover the actual Princess's single counterpart directive")
    return value


def put(state: GameState, value: Session | HighDirection) -> None:
    kind = "princess_sex_session" if isinstance(value, Session) else "princess_sex_direction"
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))
