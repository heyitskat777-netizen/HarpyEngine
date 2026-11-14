"""Actual native Pilot non-Play use, without a borrowed body or invented effect."""

from girlframe.engine import m3_easy_target as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorView, SceneCast
from girlframe.services.onboarding import WorkflowError


def matches(value: rules.Reaction) -> bool:
    return (
        value.urge == "use"
        and value.actor.kind == "pilot"
        and value.performer == value.actor
        and value.play is None
    )


def primary(
    state: GameState,
    value: rules.Reaction,
    source: rules.Session,
    scene: SceneCast,
    actor: ActorView,
) -> None:
    """Require the real original native Girl's available exterior body.

    Shared non-Play use checks prove the original source/response, common location,
    actual performance and independently owned consequence. Historical callers use
    the immutable birth state and bindings. An explicit Play keeps its own route;
    this factual performance grants no roll, payment, consent or injury.
    """
    sheet = state.sheets.get(value.actor.entity)
    if (
        not matches(value)
        or sheet is None
        or sheet.character_id != value.actor.incarnation
        or current_ref(state, value.controller) != value.actor
        or value.actor == source.actor
        or actor.ref != value.actor
        or actor.rules != "girl_frame"
        or actor.controller != value.controller
        or not actor.alive
        or sheet.medical_state != "fit"
        or actor.inside_frame is not False
        or actor.occupied_frame_instance is not None
        or actor.subsumed
        or actor.vitals_active is False
        or actor.offstage_source
        or actor.custody not in (None, "free")
        or is_helpless(state, value.actor)
        or scene.id != source.cast.id
        or scene.facilitator != source.cast.facilitator
        or scene.adjudicator is not None
        or not any(
            role.actor == value.actor and role.controller == value.controller
            for role in source.cast.roles
        )
    ):
        raise WorkflowError("Use as the original present native Girl in her available body")
