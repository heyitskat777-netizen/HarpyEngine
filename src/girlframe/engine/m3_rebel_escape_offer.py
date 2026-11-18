"""A private offer from the actual rebel actor, separate from any escape attempt."""

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_world_state import Npc

RULE = "strain.rebellion.high.2.2"
KIND = "strain_rebel_escape_offer"


class Offer(Model):
    id: str
    source_event: str
    period: str
    rebel: str
    controller: int
    handler: int
    eligible: tuple[ActorRef, ...] = Field(min_length=1)
    recipient: ActorRef | None = None
    account: str | None = None
    delivered_event: str | None = None


def offers(state: GameState) -> tuple[Offer, ...]:
    return tuple(
        Offer.model_validate_json(fact["body"]) for fact in state.facts if fact.get("kind") == KIND
    )


def put(state: GameState, offer: Offer) -> None:
    state.facts = [
        fact for fact in state.facts if (fact.get("kind"), fact.get("id")) != (KIND, offer.id)
    ] + [dict(kind=KIND, id=offer.id, body=offer.model_dump_json())]


def speaker(state: GameState, identity: str | None) -> Npc:
    world = state.world
    npc = next((x for x in world.npcs if x.id == identity), None) if world else None
    if (
        world is None
        or npc is None
        or not npc.alive
        or npc.captive_of is not None
        or "handler" not in npc.jobs
        or npc.controller == state.handler
        or not any(x.id == npc.faction and x.kind == "rebel" and x.active for x in world.factions)
    ):
        raise ValueError("Choose an active Rebel Handler controlled separately from the Handler")
    return npc
