"""Proven directional Intense benefit; never an invented Bond to spend."""

from typing import TYPE_CHECKING

from sqlalchemy import Connection

from girlframe.engine import m3_ankou as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_access import Access

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def intense_benefit(
    game: "GameService",
    c: Connection,
    state: GameState,
    beneficiary: ActorRef,
    other: ActorRef,
) -> bool:
    """Call for the actual beneficiary; the other side gains no reciprocal effect.

    This predicate cannot pay weakening/deepening, produce an acquisition cause,
    replace actual Bond depth, author desire for the other person, or supply any
    player's voluntary answer/consent. Actual core Intense remains ordinary M2.
    """
    if depth(state, beneficiary, other) == 2:
        return True
    approval = game.store.policy.m3_approval
    registry = Access(game.store).registry
    if approval is None or "plays" not in approval.subsystems or registry is None:
        return False
    try:
        registry.require_available(rules.OBSESSIVE)
    except ValueError:
        # Unavailable M3 effects never add themselves to genuine legacy M2 bonds.
        return False
    from girlframe.services.m3_ankou import prove_obsession

    return prove_obsession(game, c, state, beneficiary, other) is not None
