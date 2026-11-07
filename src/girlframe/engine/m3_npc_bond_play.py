"""A genuine NPC Bond cost and an actual job-defined Conversation performance."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, CastRole, Model, SceneCast
from girlframe.engine.m3_battle_npc import NARRATIVE

RULE = "core.core.npc-bonds"


class Request(Model):
    id: str
    holder: ActorRef
    npc: ActorRef
    controller: int
    job: str
    move: str
    source_pdf: int
    context: str = Field(min_length=1, max_length=1200)
    before_depth: Literal[1, 2]
    after_depth: Literal[0, 1]
    original_npc_json: str
    event: str


class Performance(Model):
    id: str
    request: str
    event: str
    controller: int
    cast: SceneCast
    recipients: tuple[CastRole, ...] = Field(min_length=1)
    labels: dict[str, str]
    rendition: str = Field(min_length=1, max_length=1800)


def requests(state: GameState) -> tuple[Request, ...]:
    return tuple(
        Request.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "npc_bond_request"
    )


def performances(state: GameState) -> tuple[Performance, ...]:
    return tuple(
        Performance.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "npc_bond_performance"
    )


def put(state: GameState, value: Request | Performance) -> None:
    kind = "npc_bond_request" if isinstance(value, Request) else "npc_bond_performance"
    if any(x.get("kind") == kind and x.get("id") == value.id for x in state.facts):
        raise ValueError("Preserve this original source/performance without overwriting it")
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))


def supported(job: str, move: str) -> bool:
    return job in NARRATIVE and NARRATIVE[job][0] == move


def done(state: GameState, identity: str) -> Performance | None:
    return next((x for x in performances(state) if x.request == identity), None)
