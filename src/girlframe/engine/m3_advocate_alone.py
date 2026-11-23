"""Owned decisions in an original private Advocate conversation."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model

RULE = "handler-playbook.advocate.get-them-alone"
Order = Literal["amuse", "silence"]


class Answer(Model):
    text: str = Field(min_length=1, max_length=1200)
    event: str


class Effect(Model):
    tag: str
    order: str
    event: str


class Conversation(Model):
    id: str
    handler: ActorRef
    girl: ActorRef
    channel: int
    scene: str
    event: str
    question: str = Field(min_length=1, max_length=1200)
    order: Order
    answer: Answer | None = None
    effect: Effect | None = None


def records(state: GameState) -> tuple[Conversation, ...]:
    return tuple(
        Conversation.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "advocate_conversation"
    )


def put(state: GameState, value: Conversation) -> None:
    state.facts = [
        x
        for x in state.facts
        if (x.get("kind"), x.get("id")) != ("advocate_conversation", value.id)
    ] + [dict(kind="advocate_conversation", id=value.id, body=value.model_dump_json())]
