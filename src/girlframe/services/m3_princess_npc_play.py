"""Actual job-defined NPC Conversation in one original high Princess directive."""

import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_princess_sex as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_bonds import is_helpless
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_alpha_sex import asleep
from girlframe.engine.m3_battle_npc import NARRATIVE
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def options(game: "GameService", state: GameState, value: rules.Session) -> list[dict[str, str]]:
    from girlframe.services.m3_access import Access

    npc = (
        next((x for x in state.world.npcs if x.id == value.target.entity), None)
        if value.target.kind == "npc" and state.world
        else None
    )
    if (
        npc is None
        or not npc.alive
        or npc.controller != value.counterpart
        or npc.source_kind is not None
        or "director" in npc.jobs
        or is_helpless(state, value.target)
        or asleep(state, value.target)
    ):
        return []
    registry = Access(game.store).registry
    assert registry is not None
    result = []
    for job in npc.jobs:
        if job not in NARRATIVE:
            continue
        try:
            registry.require_available("npc.npc." + job.replace("_", "-"))
        except ValueError:
            continue
        result.append(dict(id=job, label=job.replace("_", " ") + ": " + NARRATIVE[job][0]))
    return result


def _body(game: "GameService", c: Connection, state: GameState, value: rules.Session) -> None:
    from girlframe.services.m3_actor_history import snapshot_profiles
    from girlframe.services.m3_oldgen_sex import _npc_space
    from girlframe.services.m3_princess_npc import _prove_npc_contact

    bindings = snapshot_profiles(c, game.store.campaign_id, state)
    npc = resolve(state, value.target, bindings, require_current_profile=False)
    author = resolve(state, value.actor, bindings, require_current_profile=False)
    _prove_npc_contact(game, c, value)
    _npc_space(game, c, state, npc)
    if (
        not npc.alive
        or npc.offstage_source
        or npc.custody not in (None, "free")
        or not author.alive
        or author.offstage_source
        or npc.controller != value.counterpart
        or author.controller != value.caster
        or npc.vessel_id != value.target_vessel
        or author.vessel_id != value.actor_vessel
        or npc.cell is None
        or npc.cell != author.cell
        or is_helpless(state, value.target)
        or asleep(state, value.target)
        or not all(
            any(x.actor == ref and x.controller == controller for x in value.cast.roles)
            for ref, controller in ((value.target, value.counterpart), (value.actor, value.caster))
        )
    ):
        raise WorkflowError(
            "Preserve the original available NPC, controller and actual source bodies"
        )


def _current(game: "GameService", c: Connection, state: GameState, value: rules.Session) -> None:
    from girlframe.services.m3_enforcement_initiative import _cast

    _body(game, c, state, value)
    if _cast(game, c, state, value.cast.channel) != value.cast:
        raise WorkflowError("Keep the original scene and people for the immediate NPC Conversation")


def select(
    game: "GameService",
    c: Connection,
    state: GameState,
    value: rules.Session,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services.m3_princess_sex import _strict

    _strict(answer, answer.options, text=True)
    if (
        value.tier != "high"
        or value.phase != "direction"
        or value.direction
        or value.npc_direction is not None
        or value.action != action["id"]
        or value.target.kind != "npc"
        or row["actor_id"] != str(value.caster)
        or row["kind"] != "princess_sex_direct"
        or len(answer.options) != 1
        or answer.options[0] not in {x["id"] for x in options(game, state, value)}
    ):
        raise WorkflowError(
            "Choose a supported actual NPC Conversation; other effects need human adjudication "
            "and their source adapter, and remain pending"
        )
    _current(game, c, state, value)
    direction = rules.NpcDirection(
        id=value.id + ":npc-direction",
        session=value.id,
        action=action["id"],
        actor=value.target,
        controller=value.counterpart,
        author=value.actor,
        author_controller=value.caster,
        cast=value.cast,
        job=answer.options[0],
        move=NARRATIVE[answer.options[0]][0],
        context=answer.text,
        selected_choice=row["id"],
        selected_event=action["data"]["response_event"],
    )
    rules.put(
        state, value.model_copy(update=dict(npc_direction=direction, phase="npc_performance"))
    )
    game.request(c, action, value.counterpart, "princess_sex_npc_perform")


def _choice(
    game: "GameService",
    c: Connection,
    value: rules.Session,
    identity: str,
    event: str,
    owner: int,
    kind: str,
) -> ChoiceAnswer:
    from girlframe.services.m3_dose_up import _response

    answer = _response(game, c, value.action or "", identity, event, owner, kind)
    audit = c.scalar(
        sa.select(t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    )
    row = (
        c.execute(
            sa.select(t.m2["m2_choices"]).where(
                t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_choices"].c.id == identity,
            )
        )
        .mappings()
        .one()
    )
    if (
        audit is None
        or json.loads(audit).get("action_id") != value.action
        or json.loads(audit).get("choice_id") != identity
        or row["state"] != "answered"
    ):
        raise WorkflowError("Recover the original NPC directive's actual owned response event")
    return answer


def prove_direction(
    game: "GameService",
    c: Connection,
    state: GameState,
    value: rules.Session,
) -> rules.NpcDirection:
    from girlframe.services.m3_handler_advancements import _history

    direction = value.npc_direction
    if direction is None:
        raise WorkflowError("Recover this original Princess's actual NPC directive")
    born = _history(c, game, direction.selected_event)
    original = rules.get(born, value.id)
    answer = _choice(
        game,
        c,
        value,
        direction.selected_choice,
        direction.selected_event,
        value.caster,
        "princess_sex_direct",
    )
    if (
        (
            direction.session,
            direction.action,
            direction.actor,
            direction.controller,
            direction.author,
            direction.author_controller,
            direction.cast,
        )
        != (
            value.id,
            value.action,
            value.target,
            value.counterpart,
            value.actor,
            value.caster,
            value.cast,
        )
        or original.npc_direction
        != direction.model_copy(
            update=dict(
                performance_choice=None,
                performance_event=None,
                rendition=None,
            )
        )
        or original.phase != "npc_performance"
        or original.direction is not None
        or value.direction is not None
        or value.tier != "high"
        or value.effect_event != original.effect_event
        or direction.job not in NARRATIVE
        or direction.move != NARRATIVE[direction.job][0]
        or direction.job not in {x["id"] for x in options(game, born, value)}
        or answer != ChoiceAnswer(options=(direction.job,), text=direction.context)
    ):
        raise WorkflowError("Retain the actual Princess decision and exact original NPC job move")
    _body(game, c, born, value)
    if direction.performance_event:
        performed = _history(c, game, direction.performance_event)
        finished = rules.get(performed, value.id)
        actual = _choice(
            game,
            c,
            value,
            direction.performance_choice or "",
            direction.performance_event,
            value.counterpart,
            "princess_sex_npc_perform",
        )
        if (
            finished.npc_direction != direction
            or finished.phase != "complete"
            or finished.completed_event != direction.performance_event
            or value.phase != "complete"
            or value.completed_event != direction.performance_event
            or actual != ChoiceAnswer(options=("perform",), text=direction.rendition or "")
            or direction.job not in {x["id"] for x in options(game, performed, value)}
        ):
            raise WorkflowError("Prove the original NPC controller's actual fixed-move performance")
        _body(game, c, performed, value)
    elif (
        direction.performance_choice
        or direction.rendition
        or value.phase != "npc_performance"
        or value.completed_event
    ):
        raise WorkflowError("The actual NPC performance remains owed, never acknowledged away")
    return direction


def perform(
    game: "GameService",
    c: Connection,
    state: GameState,
    value: rules.Session,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services.m3_princess_sex import _strict

    _strict(answer, ("perform",), text=True)
    direction = prove_direction(game, c, state, value)
    if (
        value.phase != "npc_performance"
        or direction.performance_event
        or value.action != action["id"]
        or row["kind"] != "princess_sex_npc_perform"
        or row["actor_id"] != str(value.counterpart)
        or direction.job not in {x["id"] for x in options(game, state, value)}
    ):
        raise WorkflowError("Only the original NPC controller performs this exact selected move")
    _current(game, c, state, value)
    rules.put(
        state,
        value.model_copy(
            update=dict(
                npc_direction=direction.model_copy(
                    update=dict(
                        performance_choice=row["id"],
                        performance_event=action["data"]["response_event"],
                        rendition=answer.text,
                    )
                )
            )
        ),
    )
