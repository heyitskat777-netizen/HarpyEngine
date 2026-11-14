"""Finite learned Bonded delegation to the original Pair's actual Vatgrown session."""

import json
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_bonded as bonded
from girlframe.engine import m3_vatgrown_plays as vatgrown
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_learned_play_state import LearnedSexLink, put_learned_sex_link
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def parent_lesson(state: GameState, child: vatgrown.Session) -> str | None:
    return bonded.get(state, child.bonded_source).learned_source if child.bonded_source else None


def _audit(
    game: "GameService", c: Connection, event: str, kind: str, owner: int, child: str
) -> None:
    row = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    ).first()
    if (
        row is None
        or row.kind != kind
        or row.actor_id != str(owner)
        or json.loads(row.payload_json).get("source") != child
    ):
        raise WorkflowError("Recover this exact original Vatgrown source and human author")


def _child(
    game: "GameService", c: Connection, state: GameState, parent: bonded.Source
) -> vatgrown.Session:
    links = [x for x in bonded.records(state, bonded.Delegation) if x.source == parent.id]
    if len(links) != 1:
        raise WorkflowError("Recover the one original Pair Vatgrown child")
    link = links[0]
    birth = _history(c, game, link.event)
    original_link = next(
        (x for x in bonded.records(birth, bonded.Delegation) if x.id == link.id), None
    )
    child = vatgrown.get(state, link.session)
    original = vatgrown.get(birth, child.id)
    if (
        parent.route != "delegated"
        or parent.delegated_rule != vatgrown.SEX
        or parent.changeling_source is not None
        or parent.action is not None
        or parent.effect_event is not None
        or original_link is None
        or any(
            getattr(link, x) != getattr(original_link, x)
            for x in ("id", "source", "session", "rule", "actor", "target", "event")
        )
        or (link.actor, link.target, link.rule) != (parent.actor, parent.target, vatgrown.SEX)
        or (child.actor, child.target, child.bonded_source)
        != (parent.actor, parent.target, parent.id)
        or child.caster != parent.controllers.get(child.actor.token)
        or child.counterpart != parent.controllers.get(child.target.token)
        or child.cast != parent.cast
        or child.actor_vessel != parent.vessels.get(child.actor.token)
        or child.target_vessel != parent.vessels.get(child.target.token)
        or child.learned_source is not None
        or child.changeling_source is not None
        or child.proposed_event != link.event
        or any(
            getattr(child, x) != getattr(original, x)
            for x in (
                "id",
                "actor",
                "target",
                "caster",
                "counterpart",
                "cast",
                "registry",
                "proposed_event",
                "proposal",
                "bonded_source",
                "learned_source",
                "changeling_source",
                "actor_vessel",
                "target_vessel",
            )
        )
        or original.phase != "invited"
        or original.action is not None
        or original.bound_event is not None
        or original.consent_event is not None
        or original.effect_event is not None
        or original.completed_event is not None
        or original.learning_event is not None
        or original.departed_event is not None
        or original.question_event is not None
        or original.answer_event is not None
        or original.discipline is not None
    ):
        raise WorkflowError("Preserve this original Pair rule, independent people and source birth")
    _audit(game, c, child.proposed_event, "m3.vatgrown_sex_invited", child.caster, child.id)
    return child


def binding_child(
    game: "GameService",
    c: Connection,
    state: GameState,
    parent: bonded.Source,
    lesson: LearnedSexLink,
) -> vatgrown.Session:
    child = _child(game, c, state, parent)
    if (
        parent.learned_source != lesson.id
        or lesson.rule_id != bonded.SEX
        or lesson.session != parent.id
        or (lesson.actor, lesson.target) != (child.actor, child.target)
        or child.consent_event is None
        or child.action is None
        or child.bound_event is None
    ):
        raise WorkflowError(
            "Bind only the exact accepted parent lesson and original Vatgrown child"
        )
    _audit(game, c, child.consent_event, "m3.vatgrown_sex_consent", child.counterpart, child.id)
    accepted = vatgrown.get(_history(c, game, child.consent_event), child.id)
    if (
        accepted.phase != "accepted"
        or accepted.consent_event != child.consent_event
        or accepted.consent_account != child.consent_account
        or accepted.action is not None
        or accepted.bound_event is not None
        or any(
            getattr(accepted, key) != getattr(child, key)
            for key in (
                "actor",
                "target",
                "caster",
                "counterpart",
                "cast",
                "proposed_event",
                "bonded_source",
                "learned_source",
                "changeling_source",
            )
        )
    ):
        raise WorkflowError(
            "The actual child counterpart must independently confirm before the Play"
        )
    action = game.action(c, child.action)
    meta = action["data"].get(vatgrown.PLAY, {})
    if (
        str(action["actor_id"]) != child.actor.entity
        or action["scene_id"] != child.cast.id
        or int(action["channel_id"]) != child.cast.channel
        or action["data"].get("play") != vatgrown.PLAY
        or action["data"].get("prepared", {}).get("source_work") != child.id
        or meta.get("session") != child.id
        or meta.get("bonded_source") != parent.id
        or meta.get("bonded_lesson") != lesson.id
        or meta.get("learned_source") is not None
        or meta.get("changeling_source") is not None
        or meta.get("actor") != child.actor.model_dump(mode="json")
        or meta.get("target") != child.target.model_dump(mode="json")
        or meta.get("caster") != child.caster
        or meta.get("counterpart") != child.counterpart
        or meta.get("cast") != child.cast.model_dump(mode="json")
    ):
        raise WorkflowError("Reserve the parent lesson only for this actual child's one Action")
    return child


def _unused(
    game: "GameService", c: Connection, state: GameState, parent: bonded.Source
) -> vatgrown.Session:
    child = _child(game, c, state, parent)
    link = next(x for x in bonded.records(state, bonded.Delegation) if x.source == parent.id)
    actions = t.m2["m2_actions"]
    if (
        child.action is not None
        or child.bound_event is not None
        or child.effect_event is not None
        or child.completed_event is not None
        or child.learning_event is not None
        or child.departed_event is not None
        or child.question_event is not None
        or child.answer_event is not None
        or child.discipline is not None
        or link.action is not None
        or link.completed_event is not None
        or parent.completed_event is not None
        or c.scalar(
            sa.select(actions.c.id).where(
                actions.c.campaign_id == game.store.campaign_id,
                sa.or_(
                    sa.func.json_extract(actions.c.body_json, "$.prepared.source_work") == child.id,
                    sa.func.json_extract(actions.c.body_json, "$.vatgrown_sex.session") == child.id,
                ),
            )
        )
    ):
        raise WorkflowError(
            "Keep the actual Action, receipt and costs; release only an unused child"
        )
    return child


def release(
    game: "GameService", c: Connection, state: GameState, identity: str, owner: int, event: str
) -> None:
    from girlframe.services.m3_bonded import prove
    from girlframe.services.m3_learned_sex import get

    value = vatgrown.get(state, identity)
    parent = prove(game, c, state, value.bonded_source or "")
    child = _unused(game, c, state, parent)
    if parent.phase != "bound" or child.phase not in ("declined", "withdrawn"):
        raise WorkflowError("Release only the actual unused declined or withdrawn Vatgrown child")
    if (
        owner != (child.counterpart if child.phase == "declined" else child.caster)
        or child.phase == "declined"
        and child.consent_event != event
    ):
        raise WorkflowError(
            "Only the actual child counterpart declines or its original owner withdraws"
        )
    lesson = get(state, parent.learned_source) if parent.learned_source else None
    if lesson and (
        lesson.action or lesson.roll_event or lesson.used_event or lesson.released_event
    ):
        raise WorkflowError("Release only this exact unused original parent lesson")
    bonded.put(
        state,
        bonded.DelegationRelease(
            id=parent.id + ":release",
            source=parent.id,
            session=child.id,
            actor=parent.actor,
            controller=owner,
            outcome="declined" if child.phase == "declined" else "withdrawn",
            event=event,
        ),
    )
    if lesson is not None:
        put_learned_sex_link(
            state,
            lesson.model_copy(
                update={
                    "released_event": event,
                    "released_kind": "delegation_" + child.phase,
                }
            ),
        )
    bonded.put(state, parent.model_copy(update={"phase": child.phase}))


def prove_release(
    game: "GameService", c: Connection, state: GameState, parent: bonded.Source
) -> None:
    releases = [x for x in bonded.records(state, bonded.DelegationRelease) if x.source == parent.id]
    if not releases:
        if parent.phase in ("declined", "withdrawn") and any(
            x.source == parent.id for x in bonded.records(state, bonded.Delegation)
        ):
            raise WorkflowError("Recover the original Vatgrown child release evidence")
        return
    if len(releases) != 1:
        raise WorkflowError("Preserve the one original delegated release")
    value = releases[0]
    child = _unused(game, c, state, parent)
    saved = _history(c, game, value.event)
    ended = vatgrown.get(saved, child.id)
    if (
        value not in bonded.records(saved, bonded.DelegationRelease)
        or (value.actor, value.session, value.outcome) != (parent.actor, child.id, parent.phase)
        or child.phase != value.outcome
        or ended.phase != value.outcome
        or bonded.get(saved, parent.id).phase != value.outcome
        or value.controller != (child.counterpart if value.outcome == "declined" else child.caster)
        or value.outcome == "declined"
        and (child.consent_event != value.event or ended.consent_event != value.event)
    ):
        raise WorkflowError("Preserve this original human's exact no-effect child release")
    _audit(
        game,
        c,
        value.event,
        "m3.vatgrown_sex_" + ("consent" if value.outcome == "declined" else "withdrawn"),
        value.controller,
        child.id,
    )


def released_parent(
    game: "GameService", c: Connection, state: GameState, child: vatgrown.Session
) -> bool:
    """Released sources remain readable without granting a fresh delegation."""
    identity = parent_lesson(state, child)
    if child.bonded_source is None:
        return False
    parent_state = bonded.get(state, child.bonded_source)
    if identity is None and parent_state.phase not in ("declined", "withdrawn"):
        return False
    from girlframe.services.m3_bonded import prove
    from girlframe.services.m3_learned_sex import get

    if identity is not None and get(state, identity).released_event is None:
        return False
    parent = prove(game, c, state, child.bonded_source or "")
    if _child(game, c, state, parent) != child:
        raise WorkflowError("Recover this exact original released child")
    return True
