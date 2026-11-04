"""Supply penalties are pre-roll effects, distinct from post-roll Tags and their owners."""

from typing import Any

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef


def modifiers(state: GameState, period: str, owner: ActorRef) -> list[dict[str, Any]]:
    return [
        {"id": x.id, "source": "missed_supply", "amount": x.amount}
        for x in state.supply_losses
        if x.period == period and x.owner == owner and x.action is None
    ]


def consume(
    state: GameState, period: str, owner: ActorRef, expected: list[dict[str, Any]], action: str
) -> None:
    if modifiers(state, period, owner) != expected:
        raise ValueError(
            "STALE_SUPPLY: recover this unrolled Play and confirm its actual modifiers"
        )
    selected = {x["id"] for x in expected}
    state.supply_losses = [
        x.model_copy(update={"action": action}) if x.id in selected else x
        for x in state.supply_losses
    ]
