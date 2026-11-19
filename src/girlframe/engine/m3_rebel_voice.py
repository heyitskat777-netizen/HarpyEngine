"""A real Rebel source, the original voice and its original Cadre."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model

RULE = "strain.rebellion.high.5.1"
KIND = "strain_rebel_voice"


class Voice(Model):
    id: str
    source: str
    handler: ActorRef
    issuer: ActorRef
    controller: int
    girls: tuple[ActorRef, ...]
    prepared: str | None = None


def voices(state: GameState) -> tuple[Voice, ...]:
    return tuple(Voice.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND)


def save(state: GameState, value: Voice) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, value.id)] + [
        dict(kind=KIND, id=value.id, body=value.model_dump_json())
    ]
