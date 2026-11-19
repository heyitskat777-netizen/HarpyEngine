"""An original Handler can spend an advancement on a different book's Play."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_play_state import DRESS_RULE

RULE = "handler-advancement.handler-advancement.take-a-play"


class Acquisition(Model):
    id: str
    award: str
    handler: ActorRef
    appointment: str
    event: str
    rule: Literal["handler-playbook.dogrunner.dress-them-down"] = DRESS_RULE
    book: Literal["Dogrunner"] = "Dogrunner"
    account: str = Field(min_length=1, max_length=1200)


def acquisitions(state: GameState) -> tuple[Acquisition, ...]:
    return tuple(
        Acquisition.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "borrowed_handler_play"
    )


def put(state: GameState, value: Acquisition) -> None:
    state.facts.append(
        dict(kind="borrowed_handler_play", id=value.id, body=value.model_dump_json())
    )
