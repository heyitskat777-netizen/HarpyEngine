"""The printed High Void revelation and its original scene audience."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import CastRole, Model

RULE = "strain.void.high.5.1"
KIND = "strain_void_revelation"
Play = Literal["recontextualize_void", "reveal_near_disaster"]
PLAYS: tuple[tuple[Play, str], ...] = (
    ("recontextualize_void", "Recontextualize the Void"),
    ("reveal_near_disaster", "Reveal how close disaster is"),
)


class Revelation(Model):
    id: str
    event: str
    scene: str
    cast_revision: int
    handler: int
    play: Play
    recipients: tuple[CastRole, ...] = Field(min_length=1)
    account: str = Field(min_length=1, max_length=1200)


def revelations(state: GameState) -> tuple[Revelation, ...]:
    return tuple(
        Revelation.model_validate_json(fact["body"])
        for fact in state.facts
        if fact.get("kind") == KIND
    )


def commit(state: GameState, value: Revelation) -> None:
    if value.handler != state.handler or any(x.id == value.id for x in revelations(state)):
        raise ValueError("Record the actual Handler's source-bound revelation once")
    state.facts.append(dict(kind=KIND, id=value.id, body=value.model_dump_json()))
