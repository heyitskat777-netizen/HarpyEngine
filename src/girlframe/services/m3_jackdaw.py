"""Recover actual Jackdaw interference without disclosing its provenance to a recipient."""

from sqlalchemy import Connection

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorView
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_jackdaw import KIND, ranges
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError


def has_interference(state: GameState) -> bool:
    return any(x.get("kind") == KIND for x in state.facts)


def require_audible(
    c: Connection, campaign: str, state: GameState, conversation: tuple[ActorView, ...]
) -> None:
    if state.world is None or not has_interference(state):
        return
    bodies = tuple(
        x
        for x in conversation
        if x.rules in ("girl_frame", "handler_girl")
        and x.offstage_source is None
        and x.cell is not None
    )
    if not bodies:
        return
    bound = profiles(c, campaign)
    active = {x.id for x in state.world.gorgons if x.alive and "jackdaw" in x.types}
    for original in ranges(state):
        if original.actor.entity not in active or not any(
            x.cell in original.range.cells for x in bodies
        ):
            continue
        actual = resolve(state, original.actor, bound, require_current_profile=False)
        if actual.offstage_source is None and actual.cell == original.origin:
            raise WorkflowError(
                "No verified communication route reaches the original recipient from this position."
            )
