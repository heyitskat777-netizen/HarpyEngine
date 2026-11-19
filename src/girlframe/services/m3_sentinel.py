"""Apply the printed sensor restriction to actual actors occupying Corrupted terrain."""

from sqlalchemy import Connection

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_sentinel import already_corrupted
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError


def require_sensors(c: Connection, campaign: str, state: GameState, actor: ActorRef) -> None:
    world = state.world
    if world is None or not world.corrupted_cells or actor.kind != "pilot":
        return
    actual = resolve(state, actor, profiles(c, campaign), require_current_profile=False)
    if actual.rules == "girl_frame" and already_corrupted(world, actual.cell):
        raise WorkflowError("Corrupted terrain blocks Check Your Sensors in this actual square")
