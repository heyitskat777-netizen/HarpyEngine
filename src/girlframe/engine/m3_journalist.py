"""Source-bound NPC job requests with effects owned by the original Girl."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model

RULE = "npc.npc.journalist"
FAMILY = "npc.npc.family"
PSYCHOLOGIST = "npc.npc.psychologist"
PUBLIC_RELATIONS = "npc.npc.public-relations"
KIND = "journalist_question"
Job = Literal["journalist", "family", "psychologist", "public_relations"]
RULES: dict[Job, str] = {
    "journalist": RULE,
    "family": FAMILY,
    "psychologist": PSYCHOLOGIST,
    "public_relations": PUBLIC_RELATIONS,
}
Response = Literal["answer", "decline"]


class Question(Model):
    id: str
    scene: str
    channel: int
    reporter: ActorRef
    controller: int
    girl: ActorRef
    question: str = Field(min_length=1, max_length=1200)
    tag: str | None = Field(
        default=None, min_length=1, max_length=120, exclude_if=lambda x: x is None
    )
    identity_label: str | None = Field(
        default=None, min_length=1, max_length=120, exclude_if=lambda x: x is None
    )
    job: Job = Field(default="journalist", exclude_if=lambda value: value == "journalist")
    response: Response | None = None
    reply: str | None = None
    response_event: str | None = None
    replaced_identity: str | None = Field(default=None, exclude_if=lambda x: x is None)
    unmarked_identity: str | None = Field(default=None, exclude_if=lambda x: x is None)

    @model_validator(mode="after")
    def effect_shape(self) -> "Question":
        if self.job == "psychologist":
            if self.tag is not None or self.identity_label is None or self.response == "decline":
                raise ValueError("The Psychologist's directive supplies an actual new Identity")
        elif (
            self.tag is None
            or self.identity_label is not None
            or self.replaced_identity is not None
        ):
            raise ValueError("This original request supplies its actual conditional Tag")
        needs_unmark = self.job == "public_relations" and self.response == "answer"
        if needs_unmark != (self.unmarked_identity is not None):
            raise ValueError("A met Public Relations expectation unmarks an actual Identity")
        return self


def questions(state: GameState) -> tuple[Question, ...]:
    return tuple(
        Question.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def save(state: GameState, question: Question) -> None:
    state.facts = [
        x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, question.id)
    ] + [dict(kind=KIND, id=question.id, body=question.model_dump_json())]
