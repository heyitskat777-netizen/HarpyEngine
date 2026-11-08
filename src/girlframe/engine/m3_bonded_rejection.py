"""Finite real-Play attempts at an original owner's source-only Tag rejection."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

Play = Literal["keep_your_head", "check_sensors", "engage", "flirt", "dive_deep"]
PLAYS = {
    "keep_your_head": "Keep Your Head",
    "check_sensors": "Check Your Sensors",
    "engage": "Engage",
    "flirt": "Flirt",
    "dive_deep": "Dive Deep",
}


class Request(Model):
    id: str
    source: str
    resolution: str
    decision: str
    tag: str
    owner: ActorRef
    controller: int
    cast: SceneCast
    play: Play
    account: str
    target: ActorRef | None
    event: str


class Attempt(Model):
    id: str
    request: str
    action: str
    owner: ActorRef
    event: str


class Release(Model):
    id: str
    attempt: str
    action: str
    event: str


class Finding(Model):
    id: str
    request: str
    attempt: str
    owner: ActorRef
    controller: int
    action: str
    action_sha256: str
    roll_event: str
    receipt_sha256: str
    achieved: bool
    account: str
    event: str


KINDS: dict[type[Model], str] = {
    Request: "bonded_rejection_request",
    Attempt: "bonded_rejection_attempt",
    Release: "bonded_rejection_release",
    Finding: "bonded_rejection_finding",
}


def identity(kind: str, *parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, "girlframe:bonded-rejection:" + kind + ":" + ":".join(parts)))


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def get[T: Model](state: GameState, model: type[T], token: str) -> T:
    value = next((x for x in records(state, model) if x.model_dump()["id"] == token), None)
    if value is None:
        raise ValueError("Recover the actual original rejection-Play source")
    return value


def put(state: GameState, value: Model) -> None:
    kind, token = KINDS[type(value)], str(value.model_dump()["id"])
    if any(x.get("kind") == kind and x.get("id") == token for x in state.facts):
        raise ValueError("Preserve every actual rejection attempt and owned outcome")
    state.facts.append(dict(kind=kind, id=token, body=value.model_dump_json()))
