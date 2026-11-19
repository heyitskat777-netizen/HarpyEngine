"""Apply the Sentinel's sensor and communication restrictions to actual positions."""

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


def require_communication(
    c: Connection,
    campaign: str,
    state: GameState,
    speaker: ActorRef,
    recipients: tuple[ActorRef, ...],
) -> None:
    world = state.world
    if world is None or not world.corrupted_cells or not recipients:
        return
    bound = profiles(c, campaign)
    try:
        source = resolve(state, speaker, bound, require_current_profile=False).cell
        targets = tuple(
            resolve(state, actor, bound, require_current_profile=False).cell for actor in recipients
        )
    except ValueError as exc:
        raise WorkflowError(
            "Recover the original communication roles and their positions."
        ) from exc
    corrupted = already_corrupted(world, source)
    if any(
        target != source and (corrupted or already_corrupted(world, target)) for target in targets
    ):
        raise WorkflowError(
            "No verified communication route reaches the original recipient from this position."
        )


def require_order_communication(
    c: Connection, campaign: str, state: GameState, issuer: int, recipient: int
) -> None:
    if state.world is not None and state.world.corrupted_cells:
        from girlframe.engine.m3_actor_bonds import current_ref

        require_communication(
            c, campaign, state, current_ref(state, issuer), (current_ref(state, recipient),)
        )
