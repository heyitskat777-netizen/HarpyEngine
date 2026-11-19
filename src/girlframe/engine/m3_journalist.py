"""Questions and discrepancies from actual NPCs, with original Girl responses."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model

RULE = "npc.npc.journalist"
FAMILY = "npc.npc.family"
KIND = "journalist_question"
Job = Literal["journalist", "family"]
RULES: dict[Job, str] = {"journalist": RULE, "family": FAMILY}
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
    job: Job = Field(default="journalist", exclude_if=lambda value: value == "journalist")
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
