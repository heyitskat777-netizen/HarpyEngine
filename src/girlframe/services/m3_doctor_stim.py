"""Nanobots treat an actual player Stim effect without erasing its original drug."""

from typing import TYPE_CHECKING

from sqlalchemy import Connection

from girlframe.engine import m3_stim_sex as stim
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def effects(state: GameState, target: ActorRef) -> list[dict[str, str]]:
    return [
        dict(
            id="stim_helpless:" + effect.id,
            label="Remove Stim physiological Helplessness",
            source=fingerprint(effect),
        )
        for effect in stim.helpless_effects(state, target)
    ]


def remove(
    game: "GameService",
    c: Connection,
    state: GameState,
    target: ActorRef,
    selected: str,
    event: str,
    action: str,
) -> None:
    """Reuse the original source proof and the existing per-effect recovery record."""
    from girlframe.services.m3_stim_sex import prove_effect

    available = next((row for row in effects(state, target) if row["id"] == selected), None)
    if (
        target.kind != "pilot"
        or target.entity not in state.sheets
        or state.sheets[target.entity].character_id != target.incarnation
        or available is None
        or not event
        or not action
    ):
        raise WorkflowError("Select this original patient's actual active Stim Helpless source")
    effect = prove_effect(game, c, state, selected.removeprefix("stim_helpless:"))
    if (
        effect.kind != "helpless"
        or effect.target != target
        or fingerprint(effect) != available["source"]
        or effect not in stim.helpless_effects(state, target)
    ):
        raise WorkflowError("Recover this original patient's actual active Stim Helpless source")
    stim.put(
        state,
        stim.HelplessRecovery(
            id="nanobot:" + action + ":" + effect.id,
            effect=effect.id,
            effect_event=effect.event,
            target=target,
            drug=effect.drug,
            doctor_action=action,
            event=event,
        ),
    )
