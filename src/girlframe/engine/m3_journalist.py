"""An actual Journalist asks a direct question and an original Girl owns the reply."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model

RULE = "npc.npc.journalist"
KIND = "journalist_question"
Response = Literal["answer", "decline"]


class Question(Model):
    id: str
    scene: str
    channel: int
    reporter: ActorRef
    controller: int
    girl: ActorRef
    question: str = Field(min_length=1, max_length=1200)
    tag: str = Field(min_length=1, max_length=120)
    response: Response | None = None
    reply: str | None = None
    response_event: str | None = None


def questions(state: GameState) -> tuple[Question, ...]:
    return tuple(
        Question.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def save(state: GameState, question: Question) -> None:
    state.facts = [
        x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, question.id)
    ] + [dict(kind=KIND, id=question.id, body=question.model_dump_json())]
