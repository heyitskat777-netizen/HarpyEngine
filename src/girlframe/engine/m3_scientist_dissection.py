"""A Scientist's original specimen and the ordinary advancement source it supplies."""

from typing import Final

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model

TRIGGER: Final = "scientist_dissection"
KIND = "scientist_dissection"
BOOK = "handler-playbook.scientist.scientist"


class Dissection(Model):
    id: str
    handler: ActorRef
    specimen: ActorRef
    lab: str
    death: str
    event: str
    account: str = Field(min_length=1, max_length=1200)


def records(state: GameState) -> tuple[Dissection, ...]:
    return tuple(
        Dissection.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )
