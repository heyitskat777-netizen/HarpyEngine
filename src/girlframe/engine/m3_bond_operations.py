"""Actual Bond changes, distinct from restoring a saved relationship depth."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model


class Change(Model):
    id: str
    first: ActorRef
    second: ActorRef
    delta: Literal[-1, 1]
    before_depth: int = Field(ge=0, le=2)
    after_depth: int = Field(ge=0, le=2)
    event: str


def records(state: GameState) -> tuple[Change, ...]:
    return tuple(
        Change.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == "bond_change"
    )


def record(
    state: GameState,
    first: ActorRef,
    second: ActorRef,
    delta: Literal[-1, 1],
    before: int,
    after: int,
    event: str,
) -> Change:
    ordinal = sum(x.event == event for x in records(state))
    value = Change(
        id=str(
            uuid5(
                NAMESPACE_URL,
                f"girlframe:bond-change:{event}:{first.token}:{second.token}:{ordinal}",
            )
        ),
        first=first,
        second=second,
        delta=delta,
        before_depth=before,
        after_depth=after,
        event=event,
    )
    state.facts.append(dict(kind="bond_change", body=value.model_dump_json()))
    return value
