"""Actual non-rolling Sex sources retain mandatory legal-designation Tag ownership."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model


class AnimalGift(Model):
    source_kind: Literal["changeling_am", "bonded_am", "learned_am"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    id: str
    source: str
    animal: ActorRef
    target: ActorRef
    animal_role: ActorRef | None = Field(default=None, exclude_if=lambda value: value is None)
    target_role: ActorRef | None = Field(default=None, exclude_if=lambda value: value is None)
    designation: str
    event: str
    tag: str | None = None
    tag_event: str | None = None
    tag_animal: ActorRef | None = Field(default=None, exclude_if=lambda value: value is None)
    tag_target: ActorRef | None = Field(default=None, exclude_if=lambda value: value is None)


def gifts(state: GameState) -> tuple[AnimalGift, ...]:
    return tuple(
        AnimalGift.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "unrolled_animal_gift"
    )


def put(state: GameState, gift: AnimalGift) -> None:
    state.facts = [
        x
        for x in state.facts
        if not (x.get("kind") == "unrolled_animal_gift" and x.get("id") == gift.id)
    ] + [dict(kind="unrolled_animal_gift", id=gift.id, body=gift.model_dump_json())]
