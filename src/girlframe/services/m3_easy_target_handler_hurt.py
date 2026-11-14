"""The original ordinary Handler actually participates in NPC Easy Target hurt."""

from girlframe.engine import m3_easy_target as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import is_helpless
from girlframe.engine.m3_actor_state import ActorView, SceneCast
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.onboarding import WorkflowError


def participant(
    state: GameState,
    value: rules.Reaction,
    primary: rules.Reaction,
    source: rules.Session,
    scene: SceneCast,
    actor: ActorView,
) -> None:
    """Require the real original Handler before the NPC performs its bodily action.

    Shared hurt validation proves the source, actual NPC, available free living
    body and common location. Participation exempts only the matching Easy Target
    consequence; it does not replace real injury or permit another person's answer.
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
        or primary.session != source.id
        or primary.actor.kind != "npc"
        or primary.urge != "hurt"
        or primary.performer != primary.actor
        or primary.play is not None
        or scene.id != source.cast.id
        or scene.facilitator != source.cast.facilitator
        or scene.adjudicator is not None
        or not any(
            role.actor == value.actor and role.controller == value.controller
            for role in source.cast.roles
        )
    ):
        raise WorkflowError(
            "Participate as the original present Handler in actual ordinary NPC hurt"
        )
