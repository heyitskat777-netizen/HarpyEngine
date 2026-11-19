"""One saved +2 per performed Dogrunner reward, used by the original Girl."""

from typing import Any

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_private_scene import records

SOURCE = "dogrunner_private_reward"


def modifiers(state: GameState, owner: ActorRef) -> list[dict[str, Any]]:
    used = {x["id"] for x in state.facts if x.get("kind") == "dogrunner_recovery_use"}
    return [
        {"id": x.id, "source": SOURCE, "amount": 2}
        for x in records(state)
        if x.girl == owner
        and x.outcome == "dogrunner_rewarded"
        and x.tag is not None
        and x.id not in used
    ]


def consume(
    state: GameState,
    owner: ActorRef,
    expected: list[dict[str, Any]],
    action: str,
) -> None:
    if modifiers(state, owner) != expected:
        raise ValueError("STALE_REWARD: confirm the actual next Off-Duty roll and reward")
    state.facts.extend(
        dict(kind="dogrunner_recovery_use", id=x["id"], action=action) for x in expected
    )
