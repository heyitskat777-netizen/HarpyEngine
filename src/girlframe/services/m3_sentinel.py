"""Apply the Sentinel's restrictions and terrain Tags to actual positions."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_sentinel import RULE, already_corrupted
from girlframe.engine.m3_tag_markers import Marker
from girlframe.engine.m3_world_state import CorruptedCell
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

TERRAIN_TAG = "sentinel-terrain:"
TAG_LABEL = "Being in Corrupted terrain"


def terrain_tag(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    owner: int,
    marker: Marker | None = None,
) -> CorruptedCell | None:
    world = state.world
    if (
        world is None
        or not world.corrupted_cells
        or owner == int(action["actor_id"])
        or owner not in action["data"]["participants"]
    ):
        return None
    from girlframe.services import m3_tag_markers as markers
    from girlframe.services.m3_access import Access

    subject = markers.roller(state, action)
    if subject.kind != "pilot":
        return None
    try:
        Access(game.store).require_specialist_rule(RULE)
        bound = profiles(c, game.store.campaign_id)
        subject_body = resolve(state, subject, bound, require_current_profile=False)
        if subject_body.offstage_source is not None:
            return None
        cell = subject_body.cell
        terrain = next((x for x in world.corrupted_cells if x.cell == cell), None)
        if terrain is None or any(
            x.get("kind") == "sentinel_terrain_mark"
            and x.get("scene") == action["scene_id"]
            and x.get("terrain") == terrain.event
            for x in state.facts
        ):
            return None
        available = (
            (marker,) if marker is not None else markers.current(game, c, state, action, owner)
        )
        witnessed = False
        for original in available:
            if original.controller != owner:
                continue
            if original.actor is None:
                witnessed |= owner == state.handler
            else:
                body = resolve(state, original.actor, bound, require_current_profile=False)
                witnessed |= body.cell == cell and body.offstage_source is None
        if not witnessed:
            return None
        producer = game.action(c, terrain.action)
    except (WorkflowError, ValueError):
        return None
    origin = producer["data"].get("gorgon_play", {})
    if (
        producer["state"] != "complete"
        or producer["scene_id"] != terrain.scene
        or origin.get("kind") != "corrupt"
        or origin.get("advance_event") != terrain.event
        or origin.get("actor", {}).get("entity") != terrain.sentinel
    ):
        return None
    return terrain


def mark_terrain(
    state: GameState,
    action: dict[str, Any],
    terrain: CorruptedCell,
    marker: Marker,
    amount: int,
) -> None:
    state.facts.append(
        dict(
            kind="sentinel_terrain_mark",
            terrain=terrain.event,
            scene=action["scene_id"],
            action=action["id"],
            actor=marker.actor.model_dump_json() if marker.actor else "",
            controller=str(marker.controller),
            event=action["data"]["response_event"],
        )
    )
    action["data"]["modifiers"].append(
        dict(
            source="sentinel_terrain",
            tag=TERRAIN_TAG + terrain.event,
            actor=marker.controller,
            amount=amount,
        )
    )


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
