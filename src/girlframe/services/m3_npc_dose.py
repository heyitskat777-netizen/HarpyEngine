"""Finite ordinary human NPC Dose body, WorldTag and expiry port."""

from typing import Any

from sqlalchemy import Connection

from girlframe.engine import m3_dose_up as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_mockingbird import actor_tags, give_tag
from girlframe.engine.m3_passengers import passenger_view
from girlframe.engine.m3_world_state import WorldTag
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actor_history import snapshot_profiles
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_changeling_body import _fact
from girlframe.services.onboarding import WorkflowError


def body(game: GameService, c: Connection, state: GameState, target: ActorRef) -> tuple[Any, Any]:
    actual = resolve(
        state,
        target,
        snapshot_profiles(c, game.store.campaign_id, state),
        require_current_profile=False,
    )
    fact = _fact(game, c, state, target)
    if (
        target.kind != "npc"
        or actual.rules != "npc"
        or not actual.alive
        or fact.kind != "human_npc"
        or fact.vessel != actual.vessel_id
        or actual.vessel_id is None
        or actual.cell is None
        or actual.offstage_source
        or actual.custody not in (None, "free")
        or actual.inside_frame is True
        or actual.occupied_frame_instance is not None
        or passenger_view(state, target) is not None
    ):
        raise WorkflowError(
            "Use an actual available original human NPC body, not an enclosure/ride proxy"
        )
    return actual, fact


def apply(game: GameService, c: Connection, state: GameState, value: rules.Dose) -> GameState:
    for selection in value.selections:
        for component in selection.components:
            identity = "dose-up:" + value.id + ":" + component
            state = give_tag(
                state,
                profiles(c, game.store.campaign_id),
                value.target,
                value.actor,
                rules.LABELS[component],
                identity,
                value.event,
                (),
            )
            tag = next(x for x in actor_tags(state, value.target) if x.id == identity)
            if not isinstance(tag, WorldTag):
                raise WorkflowError("Recover the actual original NPC drug WorldTag")
            rules.put(
                state,
                rules.NpcDrugTag(
                    id=identity,
                    dose=value.id,
                    target=value.target,
                    component=component,
                    tag=tag,
                    event=value.event,
                ),
            )
    return state


def prove_tags(born: GameState, value: rules.Dose, components: set[str]) -> None:
    tags = [x for x in rules.records(born, rules.NpcDrugTag) if x.dose == value.id]
    if {x.component for x in tags} != components or len(tags) != len(components):
        raise WorkflowError("Recover every actual original NPC cocktail component")
    for drug in tags:
        identity = "dose-up:" + value.id + ":" + drug.component
        if (
            drug.id != identity
            or drug.target != value.target
            or drug.event != value.event
            or drug.tag.id != identity
            or drug.tag.label != rules.LABELS[drug.component]
            or ActorRef.model_validate_json(drug.tag.giver_entity) != value.actor
            or drug.tag not in actor_tags(born, value.target)
        ):
            raise WorkflowError("Recover exact NPC drug WorldTag and original giver provenance")


def remove(state: GameState, target: ActorRef, tags: set[str]) -> None:
    if state.world is None or not any(x.id == target.entity for x in state.world.npcs):
        raise WorkflowError("Recover the original drug recipient, never a replacement")
    state.world = state.world.model_copy(
        update={
            "npcs": tuple(
                x.model_copy(update={"tags": tuple(t for t in x.tags if t.id not in tags)})
                if x.id == target.entity
                else x
                for x in state.world.npcs
            )
        }
    )


def active_drug(game: GameService, c: Connection, state: GameState, target: ActorRef) -> str | None:
    """Actual proved NPC physiology, not a label or retroactive classification."""
    from girlframe.services.m3_dose_up import contact, prove
    from girlframe.services.m3_handler_advancements import _history

    for drug in rules.records(state, rules.NpcDrugTag):
        if drug.target != target or rules.expired(state, drug.dose):
            continue
        source = prove(game, c, state, drug.dose)
        if drug not in rules.records(_history(c, game, drug.event), rules.NpcDrugTag):
            raise WorkflowError("Preserve the original canonical NPC drug record")
        reach = contact(game, c, state, source.contact or "")
        actual, _ = body(game, c, state, target)
        if (
            source.target != target
            or source.punishment is not None
            or source.event != drug.event
            or actual.vessel_id != reach.target_vessel
            or actual.controller != source.target_controller
        ):
            raise WorkflowError("Recover the original NPC's active canonical Dose physiology")
        # prove validates every component against the original application snapshot.
        # The presentation Tag may already have been consumed; that does not end its clock.
        return drug.id
    return None
