"""Actual introductory prisoner custody, escape performance and source-owned finding."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_world_state import Npc

RULE = "strain.rebellion.low.4.2"


def identity(*parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, "girlframe:prisoner-escape:" + ":".join(parts)))


class Attempt(Model):
    id: str
    work: str
    source_event: str
    period: str
    handler: ActorRef
    controller: int
    appointment: str
    prisoner: ActorRef
    before: Npc
    cast: SceneCast
    account: str
    event: str


class MovementEvidence(Model):
    id: str
    attempt: str
    controller: int
    context_json: str
    event: str


class Resolution(Model):
    id: str
    attempt: str
    kind: Literal["failed", "dealt"]
    actor: ActorRef
    controller: int
    account: str
    event: str
    evidence: str | None = Field(default=None, exclude_if=lambda value: value is None)
    action: str | None = Field(default=None, exclude_if=lambda value: value is None)
    grip: str | None = Field(default=None, exclude_if=lambda value: value is None)
    before: Literal["low", "high"]
    after: Literal["low", "high"]


KINDS: dict[type[Model], str] = {
    Attempt: "prisoner_escape_attempt",
    MovementEvidence: "prisoner_escape_movement",
    Resolution: "prisoner_escape_resolution",
}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(row["body"])
        for row in state.facts
        if row.get("kind") == KINDS[model]
    )


def get[T: Model](state: GameState, model: type[T], key: str) -> T:
    result = [value for value in records(state, model) if value.model_dump()["id"] == key]
    if len(result) != 1:
        raise ValueError("Recover this actual original prisoner source")
    return result[0]


def put(state: GameState, value: Attempt | MovementEvidence | Resolution) -> None:
    if any(
        row.get("id") == value.id and row.get("kind") == KINDS[type(value)] for row in state.facts
    ):
        raise ValueError("Preserve the immutable original prisoner source")
    state.facts.append(dict(kind=KINDS[type(value)], id=value.id, body=value.model_dump_json()))


def resolution(state: GameState, attempt: Attempt) -> Resolution | None:
    values = [value for value in records(state, Resolution) if value.attempt == attempt.id]
    if len(values) > 1:
        raise ValueError("One actual attempt has one actual finding")
    return values[0] if values else None


def active(state: GameState, actor: ActorRef | None = None) -> tuple[Attempt, ...]:
    return tuple(
        value
        for value in records(state, Attempt)
        if resolution(state, value) is None and (actor is None or value.prisoner == actor)
    )
