"""One leaked Cadre incident with private parties and a public outcome."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model

RULE = "strain.rebellion.low.3.2"
KIND = "strain_cadre_leak"


class Leak(Model):
    id: str
    source: str
    handler: ActorRef
    director: str
    controller: int
    parties: tuple[ActorRef, ...]
    report: str
    demand: str | None = None
    demand_event: str | None = None
    apology: str | None = None
    death_events: tuple[str, ...] = ()
    outcome_event: str | None = None


def leaks(state: GameState) -> tuple[Leak, ...]:
    return tuple(Leak.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND)


def put(state: GameState, record: Leak) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, record.id)] + [
        dict(kind=KIND, id=record.id, body=record.model_dump_json())
    ]
