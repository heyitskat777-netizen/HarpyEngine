"""Recover actual Jackdaw interference without disclosing its provenance to a recipient."""

from sqlalchemy import Connection

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, ProfileBinding, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_jackdaw import KIND, Interference, Range, ranges
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError


def has_interference(state: GameState) -> bool:
    return any(x.get("kind") == KIND for x in state.facts)


def targets(
    state: GameState, cast: SceneCast, bound: tuple[ProfileBinding, ...], extent: Range
) -> tuple[ActorRef, ...]:
    present = []
    for role in cast.roles:
        if role.actor.kind not in ("npc", "handler"):
            continue
        actual = resolve(state, role.actor, bound, require_current_profile=False)
        if (
            actual.controller == role.controller
            and actual.rules in ("npc", "director", "handler")
            and actual.offstage_source is None
            and actual.cell in extent.cells
        ):
            present.append(actual.ref)
    return tuple(present)


def _active(c: Connection, campaign: str, state: GameState) -> tuple[Interference, ...]:
    if state.world is None or not has_interference(state):
        return ()
    bound = profiles(c, campaign)
    active = {x.id for x in state.world.gorgons if x.alive and "jackdaw" in x.types}
    effects = []
    for original in ranges(state):
        if original.actor.entity not in active:
            continue
        actual = resolve(state, original.actor, bound, require_current_profile=False)
        if actual.offstage_source is None and actual.cell == original.origin:
            effects.append(original)
    return tuple(effects)


def require_audible(
    c: Connection, campaign: str, state: GameState, conversation: tuple[ActorView, ...]
) -> None:
    for original in _active(c, campaign, state):
        if any(
            x.offstage_source is None
            and x.cell in original.range.cells
            and (
                x.rules in ("girl_frame", "handler_girl")
                if original.effect == "audible"
                else x.ref in original.victims
            )
            for x in conversation
        ):
            raise WorkflowError(
                "No verified communication route reaches the original recipient from this position."
            )


def require_action(c: Connection, campaign: str, state: GameState, actor: ActorView) -> None:
    if actor.ref.kind not in ("npc", "handler") or actor.offstage_source is not None:
        return
    if any(
        actor.ref in x.victims and actor.cell in x.range.cells for x in _active(c, campaign, state)
    ):
        raise WorkflowError("The original non-Pilot cannot act while the actual catatonia holds")
