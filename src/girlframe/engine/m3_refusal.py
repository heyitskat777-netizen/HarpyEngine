"""A source bonus changes the next actual refusal roll, never Heat or later Tags."""

from typing import Any

from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_refusal_state import RefusalBonus


def modifiers(bonuses: list[RefusalBonus], handler: int | None) -> list[dict[str, Any]]:
    waiting = [x for x in bonuses if x.action is None]
    if any(x.handler != handler for x in waiting):
        raise ValueError("STALE_CONTROL: recover the original control-slip Handler sources first")
    return [{"id": x.id, "source": "control_slips", "amount": x.amount} for x in waiting]


def consume(
    bonuses: list[RefusalBonus],
    handler: int | None,
    expected: list[dict[str, Any]],
    actor: ActorRef,
    action: str,
) -> list[RefusalBonus]:
    if actor.kind != "pilot" or not action.strip() or modifiers(bonuses, handler) != expected:
        raise ValueError("STALE_CONTROL: recover the unrolled refusal and its actual bonuses first")
    selected = {x["id"] for x in expected}
    return [
        x.model_copy(update={"action": action, "actor": actor}) if x.id in selected else x
        for x in bonuses
    ]
