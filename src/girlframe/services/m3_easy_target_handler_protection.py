"""Actual original Handler protection, as primary or participant, without proxy bodies."""

from girlframe.engine import m3_easy_target as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import is_helpless
from girlframe.engine.m3_actor_state import ActorView, SceneCast
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.onboarding import WorkflowError


def participant(
    state: GameState,
    value: rules.Reaction,
    protection: rules.NpcProtection,
    source: rules.Session,
    scene: SceneCast,
    actor: ActorView,
) -> None:
    """Require the source's actual Handler, not facilitator access or a Pilot proxy.

    The caller proves the original NPC or native Pilot performance and shared living,
    present, free body/scene requirements. This finite source adds no separate
    Play, immunity to harm, or authority to record another person's response.
    """
    if (
        value.actor.kind != "handler"
        or value.actor != source.handler
        or active_handler(state) != source.handler
        or state.handler != source.handler_controller
        or value.controller != source.handler_controller
        or actor.rules != "handler"
        or actor.controller != source.handler_controller
        or is_helpless(state, value.actor)
        or protection.actor.kind not in ("npc", "pilot")
        or protection.handler != source.handler
        or protection.target != source.actor
        or protection.session != source.id
        or scene != source.cast
        or scene != protection.cast
    ):
        raise WorkflowError(
            "Participate as the original present Handler in actual NPC or native Girl protection"
        )


def matches(value: rules.Reaction) -> bool:
    """Only original Handler non-Play protection uses this finite adapter."""
    return (
        value.urge == "protect"
        and value.actor.kind == "handler"
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
    """Prove the original ordinary Handler's actual protective body and authority.

    Shared protection validation proves original response/source, both real living
    co-present bodies, current cast, performed event and owned failure consequence.
    Historical callers pass the immutable birth state; it grants no live authority.
    No NPC, Pilot profile, roll, interception or mechanical harm is supplied here.
    """
    if (
        not matches(value)
        or value.actor != source.handler
        or active_handler(state) != source.handler
        or state.handler != source.handler_controller
        or value.controller != source.handler_controller
        or actor.rules != "handler"
        or not actor.alive
        or actor.inside_frame is True
        or actor.subsumed
        or actor.vitals_active is False
        or actor.offstage_source
        or actor.custody not in (None, "free")
        or actor.controller != source.handler_controller
        or is_helpless(state, value.actor)
        or scene.id != source.cast.id
        or scene.facilitator != source.cast.facilitator
        or scene.adjudicator is not None
        or not any(
            role.actor == value.actor and role.controller == value.controller
            for role in source.cast.roles
        )
    ):
        raise WorkflowError("Protect as the actual original present ordinary Handler")
