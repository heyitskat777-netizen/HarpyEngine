"""Recover actual Jackdaw interference without disclosing its provenance to a recipient."""

from sqlalchemy import Connection

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, ProfileBinding, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_hallucinations import immunity, records
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


def isolation(
    c: Connection, campaign: str, state: GameState, girl: ActorView, scene: str | None = None
) -> tuple[Interference, ...]:
    if girl.rules not in ("girl_frame", "handler_girl") or girl.offstage_source is not None:
        return ()
    return tuple(
        original
        for original in _active(c, campaign, state)
        if original.effect == "audible"
        and (scene is None or original.scene == scene)
        and girl.cell in original.range.cells
        and not immunity(state, girl.ref, original.event)
    )


def catatonic(c: Connection, campaign: str, state: GameState, actor: ActorView) -> bool:
    if actor.ref.kind != "pilot" or actor.offstage_source is not None or actor.cell is None:
        return False
    sources = {
        effect.source
        for effect in records(state)
        if effect.girl == actor.ref and effect.roll.result == "low"
    }
    return bool(sources) and any(
        x.actor in sources and x.effect == "audible" and actor.cell in x.range.cells
        for x in _active(c, campaign, state)
    )


def require_audible(
    c: Connection, campaign: str, state: GameState, conversation: tuple[ActorView, ...]
) -> None:
    if any(
        actor.offstage_source is None
        and actor.cell in actual.range.cells
        and (
            actor.rules in ("girl_frame", "handler_girl")
            if actual.effect == "audible"
            else actor.ref in actual.victims
        )
        for actual in _active(c, campaign, state)
        for actor in conversation
    ):
        raise WorkflowError(
            "No verified communication route reaches the original recipient from this position."
        )


def require_action(c: Connection, campaign: str, state: GameState, actor: ActorView) -> None:
    if catatonic(c, campaign, state, actor):
        raise WorkflowError("The original Girl is catatonic while in the actual Jackdaw's range")
    if actor.ref.kind not in ("npc", "handler") or actor.offstage_source is not None:
        return
    if any(
        actor.ref in x.victims and actor.cell in x.range.cells for x in _active(c, campaign, state)
    ):
        raise WorkflowError("The original non-Pilot cannot act while the actual catatonia holds")
