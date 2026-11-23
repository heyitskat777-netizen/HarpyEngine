"""The original Handler's rebellion changes the source of future pressure."""

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequences import same_handler_body

RULE = "strain.rebellion.endgame.6"
KIND = "rebel_handler_alignment"
PORTED_EFFECTS = frozenset({"strain.rebellion.low.1.2"})


class Alignment(Model):
    id: str
    handler: ActorRef
    opponent: str
    event: str
    account: str = Field(min_length=1, max_length=1200)


def current(state: GameState) -> Alignment | None:
    for raw in reversed(state.facts):
        if raw.get("kind") == KIND:
            value = Alignment.model_validate_json(raw["body"])
            if same_handler_body(state, value.handler):
                return value
    return None


def align(state: GameState, value: Alignment) -> None:
    if (
        not same_handler_body(state, value.handler)
        or current(state) is not None
        or state.world is None
        or not any(
            x.id == value.opponent and x.kind == "foundation" and x.active
            for x in state.world.factions
        )
    ):
        raise ValueError(
            "Preserve the actual original Rebel Handler and established Foundation opposition"
        )
    state.facts.append(dict(kind=KIND, id=value.id, body=value.model_dump_json()))
