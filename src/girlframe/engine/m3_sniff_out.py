"""Sealed source, saved roll and discovery scoped to the original investigator."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_hallucinations import Roll

RULE = "gorgon-type.doppleganger.sniff-you-out"
KIND = "sniff_you_out"


class Search(Model):
    id: str
    scene: str
    hunter: ActorRef
    gorgon: ActorRef
    guise: ActorRef
    gm: int
    appointment: str
    event: str
    hook: str
    roll: Roll | None = None
    bait: str | None = None
    bait_account: str | None = None
    disruption: str | None = None
    disruption_event: str | None = None
    discovered: str | None = None
    name: str | None = None
    proof: str | None = None


def records(state: GameState) -> tuple[Search, ...]:
    return tuple(
        Search.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def put(state: GameState, case: Search) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, case.id)]
    state.facts.append(dict(kind=KIND, id=case.id, body=case.model_dump_json()))
