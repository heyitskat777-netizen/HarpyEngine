"""Actual original Handler non-Play use, never a substitute Pilot or fabricated effect."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_easy_target as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_bonds import is_helpless
from girlframe.engine.m3_actor_state import ActorView, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def matches(value: rules.Reaction) -> bool:
    return (
        value.urge == "use"
        and value.actor.kind == "handler"
        and value.performer == value.actor
        and value.play is None
    )


def participant(
    state: GameState,
    value: rules.Reaction,
    primary: rules.Reaction,
    source: rules.Session,
    scene: SceneCast,
    actor: ActorView,
) -> None:
    """Validate the original Handler joining actual NPC or native Pilot use.

    The caller proves the original NPC or native Pilot source and available body
    before participation and again in immutable history. Facilitator authority
    alone is not physical presence or actual participation.
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
        or primary.actor.kind not in ("npc", "pilot")
        or primary.urge != "use"
        or primary.performer != primary.actor
        or primary.play is not None
        or scene != source.cast
    ):
        raise WorkflowError(
            "Participate as the original present Handler in actual NPC or native Girl use"
        )


def _validation(
    game: "GameService", c: Connection, value: rules.Reaction, source: rules.Session
) -> None:
    from girlframe.services.m3_dose_up import _response

    choices = t.m2["m2_choices"]
    rows = (
        c.execute(
            sa.select(choices).where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.action_id == source.id,
                choices.c.kind == "easy_target_validate:" + value.actor.token,
            )
        )
        .mappings()
        .all()
    )
    row = next((x for x in rows if json.loads(x["body_json"]).get("work") == value.id), None)
    if row is None or value.validation_event is None or row["state"] != "answered":
        raise WorkflowError("Preserve the original Handler's explicit non-Play source validation")
    answer = _response(
        game,
        c,
        source.id,
        row["id"],
        value.validation_event,
        source.handler_controller,
        "easy_target_validate:" + value.actor.token,
    )
    if answer.flag is not True or not answer.text.strip() or answer.options or answer.fields:
        raise WorkflowError("Validate only the actual non-Play use, not an unperformed effect")


def _body(
    game: "GameService",
    c: Connection,
    state: GameState,
    value: rules.Reaction,
    source: rules.Session,
    scene: SceneCast,
) -> tuple[ActorView, ActorView]:
    from girlframe.services.m3_actor_history import snapshot_profiles

    bound = snapshot_profiles(c, game.store.campaign_id, state)
    actor, ward = (
        resolve(state, ref, bound, require_current_profile=False)
        for ref in (value.actor, source.actor)
    )
    if (
        not matches(value)
        or value.actor != source.handler
        or active_handler(state) != source.handler
        or state.handler != source.handler_controller
        or value.controller != source.handler_controller
        or actor.rules != "handler"
        or actor.controller != value.controller
        or not actor.alive
        or actor.offstage_source
        or actor.custody not in (None, "free")
        or is_helpless(state, value.actor)
        or ward.rules != "girl_frame"
        or ward.controller != source.caster
        or not ward.alive
        or ward.offstage_source
        or ward.custody not in (None, "free")
        or ward.inside_frame is not False
        or actor.cell is None
        or actor.cell != ward.cell
        or not scene.open
        or scene != source.cast
        or not all(
            any(r.actor == ref and r.controller == controller for r in scene.roles)
            for ref, controller in ((value.actor, value.controller), (source.actor, source.caster))
        )
    ):
        raise WorkflowError(
            "Use the original present Handler body and actual Newgirl in this scene"
        )
    return actor, ward


def context(
    game: "GameService",
    c: Connection,
    state: GameState,
    value: rules.Reaction,
    *,
    historical: bool = False,
) -> rules.Session:
    """The original validated Handler use remains unfinished during actual participation."""
    from girlframe.services.m3_dose_up import _cast
    from girlframe.services.m3_easy_target import _session
    from girlframe.services.m3_easy_target import prove as prove_reaction

    action = game.action(c, value.session)
    source = _session(game, c, state, action)
    prove_reaction(game, c, state, value.id)
    if (
        not matches(value)
        or not rules.settled(state, source)
        or not value.validation_event
        or value.child
        or value.children
        or value.performance_event
        or value.completed_event
        or (not historical and action["state"] in ("complete", "aborted"))
    ):
        raise WorkflowError("Use the original validated Handler use before it has finished")
    _validation(game, c, value, source)
    scene = (
        next((x for x in state.scene_casts if x.id == source.cast.id), None)
        if historical
        else _cast(game, c, state, source.cast.channel)
    )
    if scene is None:
        raise WorkflowError("Preserve the actual original Handler use scene")
    _body(game, c, state, value, source, scene)
    return source


def _cohorts(
    game: "GameService", c: Connection, state: GameState, value: rules.Reaction
) -> tuple[rules.Reaction, ...]:
    from girlframe.services.m3_easy_target import prove_use_cohort

    participants = []
    for cohort in rules.records(state, rules.Reaction):
        if cohort.session != value.session or cohort.urge != "cohort" or cohort.primary != value.id:
            continue
        recorded = next(
            (x for x in rules.records(state, rules.UseCohort) if x.reaction == cohort.id), None
        )
        if recorded is not None:
            prove_use_cohort(game, c, state, recorded.id)
        if cohort.performance_event:
            if (
                recorded is None
                or recorded.outcome != "participated"
                or recorded.event != cohort.performance_event
                or cohort.exemption != value.id
            ):
                raise WorkflowError("Preserve the actual participant's own prior performance")
            participants.append(cohort)
    if bool(value.exemption) != bool(participants) or (
        value.exemption and value.exemption not in {x.id for x in participants}
    ):
        raise WorkflowError("Only actual prior participation exempts this Handler use")
    return tuple(participants)


def perform(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    value: rules.Reaction,
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services.m3_dose_up import _cast
    from girlframe.services.m3_easy_target import _consequence, _session
    from girlframe.services.m3_easy_target import prove as prove_reaction

    source = _session(game, c, state, action)
    prove_reaction(game, c, state, value.id)
    if (
        value.session != source.id
        or not rules.settled(state, source)
        or not matches(value)
        or value.child
        or value.children
        or value.performance_event
        or value.completed_event
        or action["state"] in ("complete", "aborted")
        or row["kind"] != "easy_target_child:" + value.actor.token
        or row["actor_id"] != str(value.controller)
        or answer.options
        or answer.fields
        or answer.flag is not None
        or not answer.text.strip()
    ):
        raise WorkflowError("Record only the original Handler's actual completed non-Play use")
    context(game, c, state, value)
    participants = _cohorts(game, c, state, value)
    scene = _cast(game, c, state, source.cast.channel)
    actor, ward = _body(game, c, state, value, source, scene)
    assert actor.cell is not None
    event = action["data"]["response_event"]
    use = rules.HandlerUse(
        id=str(uuid4()),
        reaction=value.id,
        session=source.id,
        actor=value.actor,
        controller=value.controller,
        target=source.actor,
        handler=source.handler,
        cast=scene,
        choice=row["id"],
        account=answer.text.strip(),
        event=event,
        cell=actor.cell,
        target_position=ward.position_sha256,
        actor_vessel=actor.vessel_id,
        target_vessel=ward.vessel_id,
    )
    rules.put(state, use)
    for cohort in participants:
        if cohort.completed_event:
            raise WorkflowError("Original participation completes only with this Handler use")
        rules.put(state, cohort.model_copy(update=dict(completed_event=event)))
    changed = value.model_copy(update=dict(performance_event=event))
    rules.put(state, changed)
    _consequence(game, c, state, action, changed, event)


def prove(game: "GameService", c: Connection, state: GameState, identity: str) -> rules.HandlerUse:
    from girlframe.services.m3_dose_up import _response
    from girlframe.services.m3_easy_target import _session
    from girlframe.services.m3_easy_target import prove as prove_reaction
    from girlframe.services.m3_handler_advancements import _history

    value = rules.get(state, rules.HandlerUse, identity)
    born = _history(c, game, value.event)
    reaction = prove_reaction(game, c, born, value.reaction)
    source = _session(game, c, born, game.action(c, value.session))
    if (
        value != rules.get(born, rules.HandlerUse, identity)
        or not matches(reaction)
        or not rules.settled(born, source)
        or reaction.child
        or reaction.children
        or reaction.performance_event != value.event
        or (value.actor, value.controller, value.target, value.handler)
        != (reaction.actor, reaction.controller, source.actor, source.handler)
    ):
        raise WorkflowError("Recover the canonical original Handler non-Play use")
    _validation(game, c, reaction, source)
    participants = _cohorts(game, c, born, reaction)
    if participants and (
        reaction.consequence != "cohort-exempt"
        or reaction.completed_event != value.event
        or any(x.completed_event != value.event for x in participants)
    ):
        raise WorkflowError("Actual participation exempts the matching Bond consequence only")
    answer = _response(
        game,
        c,
        value.session,
        value.choice,
        value.event,
        value.controller,
        "easy_target_child:" + value.actor.token,
    )
    if (
        answer.text.strip() != value.account
        or answer.options
        or answer.fields
        or answer.flag is not None
    ):
        raise WorkflowError("Only the actual original Handler records this factual completion")
    actor, ward = _body(game, c, born, reaction, source, value.cast)
    if (
        value.cell != actor.cell
        or value.target_position != ward.position_sha256
        or value.actor_vessel != actor.vessel_id
        or value.target_vessel != ward.vessel_id
    ):
        raise WorkflowError("Preserve the actual original use bodies and physical source")
    return value
