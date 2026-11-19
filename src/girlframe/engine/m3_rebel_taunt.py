"""An original radio taunt, private Handler Tag and one subsequent interaction."""

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model

RULE = "strain.rebellion.low.4.1"
KIND = "strain_rebel_taunt"


class Taunt(Model):
    id: str
    source: str
    period: str
    handler: ActorRef
    rebel: str
    controller: int
    account: str = Field(min_length=1, max_length=1200)
    radio: str | None = None
    radio_event: str | None = None
    tag: str | None = None
    tag_event: str | None = None
    girl: ActorRef | None = None
    work: str | None = None
    interaction_event: str | None = None
    interaction_period: str | None = None


def taunts(state: GameState) -> tuple[Taunt, ...]:
    return tuple(Taunt.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND)


def save(state: GameState, case: Taunt) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, case.id)] + [
        dict(kind=KIND, id=case.id, body=case.model_dump_json())
    ]
