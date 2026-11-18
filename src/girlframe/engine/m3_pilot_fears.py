"""The Directors' public-fear demand and its source-bound outcomes."""

from typing import Literal

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model

RULE = "strain.void.high.4.2"
KIND = "strain_pilot_fears"


class Response(Model):
    actor: ActorRef
    scene: str
    event: str
    account: str


class Fears(Model):
    id: str
    source: str
    period: str
    director: str
    controller: int
    handler: ActorRef
    cadre: tuple[ActorRef, ...]
    demand: str | None = None
    demand_event: str | None = None
    responses: tuple[Response, ...] = ()
    result: Literal["addressed", "discipline"] | None = None
    result_event: str | None = None
    decision: str | None = None
    evidence: str | None = None


def cases(state: GameState) -> tuple[Fears, ...]:
    return tuple(Fears.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND)


def save(state: GameState, value: Fears) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, value.id)] + [
        dict(kind=KIND, id=value.id, body=value.model_dump_json())
    ]
