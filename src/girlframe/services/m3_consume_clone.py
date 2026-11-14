"""Eat's physical trigger for the genuine purchased Frame-resident Clone source."""

from typing import TYPE_CHECKING

from sqlalchemy import Connection

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.m3_actor_history import snapshot_profiles
from girlframe.services.m3_clone_am import prove_copy
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def require_physical_target(
    game: "GameService",
    c: Connection,
    state: GameState,
    target: ActorRef,
) -> None:
    """Personhood and cast participation do not create an independently edible body.

    PDF92/p90 creates a copy hosted in the purchased/retained Frame. PDF66/p64
    requires actual jaws around a physical foe. A future real body source must
    be handled as that source, with its same-copy consequences, rather than
    being declared permanently noncorporeal by this current-source policy.
    """
    if target.kind != "clone_am":
        return
    prove_copy(game, c, state, target)
    actual = resolve(
        state,
        target,
        snapshot_profiles(c, game.store.campaign_id, state),
        require_current_profile=False,
    )
    if actual.vessel_id is None:
        raise WorkflowError(
            "SOURCE_CLONE_BODY_REQUIRED: this actual Clone AM is a mind hosted in its "
            "purchased or retained Frame, without a separately targetable physical body. "
            "Choose an actual embodied target whose source permits the lunge."
        )
    # No currently produced Clone source grants this case. Retain a distinct,
    # truthful dependency if a later actual source supplies a physical vessel.
    raise WorkflowError(
        "SOURCE_CLONE_LIFECYCLE_REQUIRED: recover this distinct physical copy's actual "
        "body source and same-copy damage, death, custody and escape operations before Eat. "
        "Do not apply them to its original Pilot by proxy."
    )
