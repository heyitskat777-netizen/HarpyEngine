"""Original participants and signed stages of a High Budget accusation."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model

RULE = "strain.budget.high.3.1"
KIND = "budget_solo_hearing"
Phase = Literal["notice", "answer", "finding", "dismissed", "review"]


class Hearing(Model):
    id: str
    period: str
    source: str
    handler: ActorRef
    girl: ActorRef
    director: str
    controller: int
    phase: Phase = "notice"
    charge: str = Field(default="", max_length=1200)
    defense: str = Field(default="", max_length=1200)
    finding: str = Field(default="", max_length=1200)
    notice_event: str | None = None
    answer_event: str | None = None
    finding_event: str | None = None


def hearings(state: GameState) -> tuple[Hearing, ...]:
    return tuple(
        Hearing.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def save(state: GameState, hearing: Hearing) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, hearing.id)] + [
        dict(kind=KIND, id=hearing.id, body=hearing.model_dump_json())
    ]
