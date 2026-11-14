"""Actual owned participation in NPC hurt, without inventing a Tag roll or immunity."""

from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_easy_target as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_state import ActorView, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actor_history import snapshot_profiles
from girlframe.services.m3_dose_up import _cast, _response
from girlframe.services.m3_easy_target_handler_hurt import participant as handler_participant
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError


def matches(state: GameState, value: rules.Reaction) -> bool:
    from girlframe.services.m3_easy_target import _npc_hurt_reaction

    primary = next((x for x in rules.records(state, rules.Reaction) if x.id == value.primary), None)
    return bool(value.urge == "cohort" and primary and _npc_hurt_reaction(primary))


def attempt(state: GameState, value: rules.Reaction) -> rules.NpcHurt | None:
    """Participation must precede the first performed bodily action, not its eventual injury."""
    if not matches(state, value):
        return None
    return next(
        (x for x in rules.records(state, rules.NpcHurt) if x.reaction == value.primary), None
    )


def _actor(
    game: GameService,
    c: Connection,
    state: GameState,
    value: rules.Reaction,
    source: rules.Session,
    scene: SceneCast,
) -> ActorView:
    bindings = snapshot_profiles(c, game.store.campaign_id, state)
    actor = resolve(state, value.actor, bindings, require_current_profile=False)
    ward = resolve(state, source.actor, bindings, require_current_profile=False)
    primary = rules.get(state, rules.Reaction, value.primary or "")
    original_handler = value.actor.kind == "handler"
    if original_handler:
        handler_participant(state, value, primary, source, scene, actor)
    if (
        value.session != source.id
        or not matches(state, value)
        or value.actor in (source.actor, primary.actor)
        or value.performance_event
        or value.completed_event
        or (not original_handler and actor.rules not in ("npc", "girl_frame"))
        or not actor.alive
        or actor.controller != value.controller
        or actor.offstage_source
        or actor.custody not in (None, "free")
        or (actor.rules == "girl_frame" and actor.inside_frame is not False)
        or actor.cell is None
        or actor.cell != ward.cell
        or scene.id != source.cast.id
        or not scene.open
        or not any(r.actor == value.actor and r.controller == value.controller for r in scene.roles)
    ):
        raise WorkflowError("Go along as your actual available body in this original hurt scene")
    return actor


def apply(
    game: GameService,
    c: Connection,
    state: GameState,
    value: rules.Reaction,
    row: dict[str, Any],
    answer: ChoiceAnswer,
    event: str,
) -> None:
    from girlframe.services.m3_easy_target import (
        _npc_hurt_context,
        _session,
        prove_npc_hurt,
    )
    from girlframe.services.m3_easy_target import (
        prove as prove_reaction,
    )

    prove_reaction(game, c, state, value.id)
    primary = prove_reaction(game, c, state, value.primary or "")
    source = _session(game, c, state, game.action(c, value.session))
    hurt = attempt(state, value)
    if (
        not matches(state, value)
        or value.performance_event
        or value.completed_event
        or answer.options not in (("participate",), ("decline",), ("missed",))
        or answer.fields
        or answer.flag is not None
        or not rules.settled(state, source)
        or not primary.validation_event
    ):
        raise WorkflowError("Choose your own original participation, decline or missed opportunity")
    outcome = answer.options[0]
    actor = None
    scene = source.cast
    if outcome == "missed":
        if hurt is None:
            raise WorkflowError("No actual NPC bodily performance has occurred yet")
        prove_npc_hurt(game, c, state, hurt.id)
    elif hurt is not None:
        raise WorkflowError("The NPC already performed; acknowledge your missed participation")
    elif outcome == "participate":
        _npc_hurt_context(game, c, state, primary)
        scene = _cast(game, c, state, source.cast.channel)
        actor = _actor(game, c, state, value, source, scene)
    rules.put(
        state,
        rules.HurtCohort(
            id=str(uuid4()),
            reaction=value.id,
            primary=primary.id,
            outcome="participated"
            if outcome == "participate"
            else "declined"
            if outcome == "decline"
            else "missed",
            hurt=hurt.id if hurt else None,
            actor=value.actor,
            controller=value.controller,
            choice=row["id"],
            account=answer.text.strip(),
            event=event,
            cast=scene,
            position=actor.position_sha256 if actor else None,
            vessel=actor.vessel_id if actor else None,
        ),
    )
    if outcome == "participate":
        rules.put(
            state,
            value.model_copy(
                update=dict(
                    performance_event=event, exemption=primary.id, consequence="cohort-exempt"
                )
            ),
        )
        rules.put(state, primary.model_copy(update=dict(exemption=value.id)))
    else:
        rules.put(
            state,
            value.model_copy(
                update=dict(
                    consequence="hurt-cohort-" + ("declined" if outcome == "decline" else "missed"),
                    completed_event=event,
                )
            ),
        )


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.HurtCohort:
    from girlframe.services.m3_easy_target import (
        _npc_hurt_context,
        _session,
        prove_npc_hurt,
    )
    from girlframe.services.m3_easy_target import (
        prove as prove_reaction,
    )

    value = rules.get(state, rules.HurtCohort, identity)
    born = _history(c, game, value.event)
    reaction = prove_reaction(game, c, born, value.reaction)
    primary = prove_reaction(game, c, born, value.primary)
    source = _session(game, c, born, game.action(c, reaction.session))
    response = _response(
        game,
        c,
        source.id,
        value.choice,
        value.event,
        value.controller,
        "easy_target_child:" + value.actor.token,
    )
    if (
        value != rules.get(born, rules.HurtCohort, identity)
        or not matches(born, reaction)
        or reaction.primary != primary.id
        or (value.actor, value.controller) != (reaction.actor, reaction.controller)
        or response.text.strip() != value.account
        or response.options
        != (
            ("participate",)
            if value.outcome == "participated"
            else ("decline",)
            if value.outcome == "declined"
            else ("missed",)
        )
        or response.fields
        or response.flag is not None
        or not rules.settled(born, source)
        or not primary.validation_event
    ):
        raise WorkflowError("Recover the actual owned hurt participation and original source")
    if value.outcome != "participated":
        if (
            reaction.performance_event
            or reaction.exemption
            or reaction.completed_event != value.event
            or reaction.consequence != "hurt-cohort-" + value.outcome
            or value.position is not None
            or value.vessel is not None
            or value.cast != source.cast
        ):
            raise WorkflowError("Preserve nonparticipation without a retroactive exemption")
        if value.outcome == "missed":
            hurt = prove_npc_hurt(game, c, born, value.hurt or "")
            if hurt.reaction != primary.id or attempt(born, reaction) != hurt:
                raise WorkflowError("Preserve the actual bodily performance preceding this answer")
        elif value.hurt is not None or attempt(born, reaction) is not None:
            raise WorkflowError("Preserve the actual decline before the NPC performed")
        return value
    source = _npc_hurt_context(game, c, born, primary, historical=True)
    if (
        reaction.performance_event != value.event
        or reaction.exemption != primary.id
        or primary.exemption != reaction.id
        or reaction.completed_event
        or reaction.consequence != "cohort-exempt"
        or value.hurt is not None
        or attempt(born, reaction) is not None
    ):
        raise WorkflowError("Recover actual participation before the original NPC bodily action")
    actor = _actor(
        game, c, born, reaction.model_copy(update=dict(performance_event=None)), source, value.cast
    )
    if (actor.position_sha256, actor.vessel_id) != (value.position, value.vessel):
        raise WorkflowError("Preserve the actual original participating body")
    return value


def verify_participants(
    game: GameService, c: Connection, state: GameState, primary: rules.Reaction
) -> None:
    """A nomination alone supplies no exemption; recorded helpers must actually remain present."""
    from girlframe.services.m3_easy_target import _session

    source = _session(game, c, state, game.action(c, primary.session))
    scene = _cast(game, c, state, source.cast.channel)
    participants = []
    for value in rules.records(state, rules.HurtCohort):
        if value.primary != primary.id or value.outcome != "participated":
            continue
        prove(game, c, state, value.id)
        reaction = rules.get(state, rules.Reaction, value.reaction)
        if reaction.performance_event != value.event or reaction.exemption != primary.id:
            raise WorkflowError("Preserve the original performed cohort and exact exemption")
        actor = _actor(
            game, c, state, reaction.model_copy(update=dict(performance_event=None)), source, scene
        )
        if actor.vessel_id != value.vessel:
            raise WorkflowError("Preserve the original participating body for this actual blow")
        participants.append(reaction.id)
    if primary.exemption is not None and primary.exemption not in participants:
        raise WorkflowError("Only actual source-proved participation exempts this NPC hurt")


def complete(
    game: GameService, c: Connection, state: GameState, primary: rules.Reaction, event: str
) -> None:
    """Only actual resolved bodily harm completes participated cohorts, not the initial account."""
    participants = []
    for value in rules.records(state, rules.HurtCohort):
        if value.primary != primary.id or value.outcome != "participated":
            continue
        prove(game, c, state, value.id)
        reaction = rules.get(state, rules.Reaction, value.reaction)
        if reaction.performance_event != value.event or reaction.exemption != primary.id:
            raise WorkflowError("Preserve the original performed cohort through actual bodily harm")
        rules.put(state, reaction.model_copy(update=dict(completed_event=event)))
        participants.append(reaction.id)
    if primary.exemption is not None and primary.exemption not in participants:
        raise WorkflowError("Only the original actual cohort exempts this hurt consequence")
