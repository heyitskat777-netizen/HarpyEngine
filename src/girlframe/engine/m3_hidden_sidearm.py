"""Exact concealed ordinary gun source and three revealed Handler choices."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

RULE = "handler-advancement.handler-advancement.hidden-sidearm"


class Acquisition(Model):
    id: str
    award: str
    handler: ActorRef
    appointment: str
    gun: str
    event: str
    account: str = Field(min_length=1, max_length=1200)


class Concealment(Model):
    id: str
    acquisition: str
    handler: ActorRef
    gun: str
    event: str
    account: str = Field(min_length=1, max_length=1200)
    reveal: str | None = None


class Reveal(Model):
    id: str
    acquisition: str
    concealment: str
    gun: str
    handler: ActorRef
    target: ActorRef
    vessel: str
    cast: SceneCast
    event: str
    account: str = Field(min_length=1, max_length=1200)
    choice: Literal["helpless", "kill", "pause"]
    phase: Literal[
        "helpless", "death", "prevented", "reconsidering", "withdrawn", "shot", "shot_helpless"
    ]
    action: str | None = None
    archive: str | None = None
    response_event: str | None = None
    response: str | None = None
    asset: str | None = None


def acquisitions(state: GameState) -> tuple[Acquisition, ...]:
    return tuple(
        Acquisition.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "hidden_sidearm_acquisition"
    )


def concealments(state: GameState) -> tuple[Concealment, ...]:
    return tuple(
        Concealment.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "hidden_sidearm_concealment"
    )


def reveals(state: GameState) -> tuple[Reveal, ...]:
    return tuple(
        Reveal.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "hidden_sidearm_reveal"
    )


def put(state: GameState, value: Acquisition | Concealment | Reveal) -> None:
    kind = {
        Acquisition: "hidden_sidearm_acquisition",
        Concealment: "hidden_sidearm_concealment",
        Reveal: "hidden_sidearm_reveal",
    }[type(value)]
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))
