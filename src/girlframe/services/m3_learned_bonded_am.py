"""One learned original Pair AM source, consumed by real no-roll participation."""

import json
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_bonded as bonded
from girlframe.engine import m3_bonded_am as am
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_learned_play_state import LearnedSexLink, put_learned_sex_link
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


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
        raise WorkflowError("Preserve this actual original AM source and its human author")


def _child(
    game: "GameService", c: Connection, state: GameState, parent: bonded.Source
) -> am.Source:
    links = [x for x in bonded.records(state, bonded.Delegation) if x.source == parent.id]
    if len(links) != 1:
        raise WorkflowError("Recover the one original learned AM no-roll child")
    link = links[0]
    child = am.source(state, link.session)
    birth = _history(c, game, child.event)
    original = am.source(birth, child.id)
    saved = next((x for x in bonded.records(birth, bonded.Delegation) if x.id == link.id), None)
    if (
        parent.learned_source is None
        or parent.route != "delegated"
        or parent.delegated_rule != am.RULE
        or parent.action is not None
        or parent.effect_event is not None
        or parent.changeling_source is not None
        or saved is None
        or link.action is not None
        or (link.actor, link.target, link.rule) != (parent.actor, parent.target, am.RULE)
        or any(
            getattr(link, k) != getattr(saved, k)
            for k in ("id", "source", "session", "rule", "actor", "target", "event")
        )
        or (child.actor, child.target, child.bonded_source)
        != (parent.actor, parent.target, parent.id)
        or child.cast != parent.cast
        or child.controllers != parent.controllers
        or child.vessels != parent.vessels
        or child.event != link.event
        or any(
            getattr(child, k) != getattr(original, k)
            for k in (
                "id",
                "bonded_source",
                "actor",
                "target",
                "controllers",
                "vessels",
                "positions",
                "cast",
                "registry",
                "event",
                "account",
                "kind",
                "action",
            )
        )
        or original.phase != "active"
        or original.effect_event is not None
        or original.completed_event is not None
        or original.withdrawn_event is not None
        or any(x.source == child.id for x in am.performances(birth))
    ):
        raise WorkflowError("Preserve actual original AM bodies, owners, consent and no-roll birth")
    _audit(
        game, c, child.event, "m3.bonded_am_started", child.controllers[child.actor.token], child.id
    )
    return child


def prove_use(
    game: "GameService",
    c: Connection,
    state: GameState,
    parent: bonded.Source,
    lesson: LearnedSexLink,
) -> None:
    from girlframe.services.m3_learned_sex import _grant, get

    if not any(x.bonded_source == parent.id for x in am.sources(state)):
        from girlframe.services.m3_learned_bonded_am_counterpart import (
            prove_use as prove_counterpart,
        )

        prove_counterpart(game, c, state, parent, lesson)
        return
    child = _child(game, c, state, parent)
    if (
        parent.learned_source != lesson.id
        or lesson.session != parent.id
        or lesson.rule_id != bonded.SEX
        or (lesson.actor, lesson.target) != (child.actor, child.target)
        or lesson.accepted is not True
        or lesson.used_event is None
        or any(
            getattr(lesson, k) is not None
            for k in ("action", "bound_event", "roll_event", "receipt_sha256", "released_event")
        )
    ):
        raise WorkflowError("Use the actual accepted parent lesson without an Action or receipt")
    used = _history(c, game, lesson.used_event)
    performances = [x for x in am.performances(used) if x.source == child.id]
    if len(performances) != 1:
        raise WorkflowError("The first actual participation consumes this no-roll lesson once")
    performed = performances[0]
    _audit(game, c, lesson.used_event, "m3.bonded_am_performed", performed.controller, child.id)
    if (
        performed.event != lesson.used_event
        or performed.actor not in (child.actor, child.target)
        or child.controllers.get(performed.actor.token) != performed.controller
        or performed not in am.performances(state)
        or am.source(used, child.id).phase != "active"
        or get(used, lesson.id).used_event != lesson.used_event
    ):
        raise WorkflowError("Preserve the actual original person's first performed participation")
    for snapshot in (used, state):
        grant = _grant(game, c, snapshot, lesson)
        if (
            grant.claimed_source != child.id
            or grant.used_event != lesson.used_event
            or grant.claimed_action is not None
            or grant.rolled_event is not None
        ):
            raise WorkflowError("Keep the actual one-use AM performance without invented dice")


def consume(
    game: "GameService", c: Connection, state: GameState, child: am.Source, event: str
) -> None:
    from girlframe.services.m3_learned_plays import _replace
    from girlframe.services.m3_learned_sex import _grant, get

    parent = bonded.get(state, child.bonded_source)
    if parent.learned_source is None:
        return
    lesson = get(state, parent.learned_source)
    if lesson.used_event is not None:
        prove_use(game, c, state, parent, lesson)
        return
    actual = _child(game, c, state, parent)
    grant = _grant(game, c, state, lesson)
    if (
        actual != child
        or child.phase != "active"
        or parent.phase != "bound"
        or lesson.accepted is not True
        or lesson.session != parent.id
        or lesson.rule_id != bonded.SEX
        or (lesson.actor, lesson.target) != (child.actor, child.target)
        or any(
            getattr(lesson, k) is not None
            for k in ("action", "bound_event", "roll_event", "receipt_sha256", "released_event")
        )
        or any(
            getattr(grant, k) is not None
            for k in ("claimed_action", "rolled_event", "claimed_source", "used_event")
        )
        or any(x.source == child.id for x in am.performances(state))
        or not event
    ):
        raise WorkflowError("Consume only this unused original no-roll source's first performance")
    _replace(state, grant.model_copy(update=dict(claimed_source=child.id, used_event=event)))
    put_learned_sex_link(state, lesson.model_copy(update=dict(used_event=event)))


def release(
    game: "GameService",
    c: Connection,
    state: GameState,
    child: am.Source,
    person: ActorRef,
    event: str,
) -> None:
    from girlframe.services.m3_learned_sex import get

    parent = bonded.get(state, child.bonded_source)
    if parent.learned_source is None:
        return
    lesson = get(state, parent.learned_source)
    actual = _child(game, c, state, parent)
    if (
        actual.phase != "withdrawn"
        or actual.withdrawn_event != event
        or actual.withdrawn_by != person
        or person not in (child.actor, child.target)
        or actual.effect_event is not None
        or actual.completed_event is not None
        or lesson.released_event is not None
        or lesson.action is not None
    ):
        raise WorkflowError("Withdraw only this exact original no-effect source")
    if lesson.used_event is None:
        if any(x.source == child.id for x in am.performances(state)):
            raise WorkflowError("A real performance cannot refund its one-use lesson")
        put_learned_sex_link(
            state,
            lesson.model_copy(
                update=dict(released_event=event, released_kind="delegation_withdrawn")
            ),
        )
    else:
        prove_use(game, c, state, parent, lesson)
    bonded.put(
        state,
        bonded.DelegationRelease(
            id=parent.id + ":release",
            source=parent.id,
            session=child.id,
            actor=parent.actor,
            controller=child.controllers[person.token],
            outcome="withdrawn",
            event=event,
        ),
    )
    bonded.put(state, parent.model_copy(update=dict(phase="withdrawn")))


def prove_release(
    game: "GameService", c: Connection, state: GameState, parent: bonded.Source
) -> None:
    if parent.learned_source is None:
        return
    from girlframe.services.m3_learned_sex import get

    releases = [x for x in bonded.records(state, bonded.DelegationRelease) if x.source == parent.id]
    if not releases:
        if parent.phase == "withdrawn" and any(
            x.source == parent.id for x in bonded.records(state, bonded.Delegation)
        ):
            raise WorkflowError("Recover the actual original AM withdrawal")
        return
    child = _child(game, c, state, parent)
    if len(releases) != 1 or child.withdrawn_by not in (child.actor, child.target):
        raise WorkflowError("Preserve the one original participant-owned withdrawal")
    value = releases[0]
    saved = _history(c, game, value.event)
    lesson = get(state, parent.learned_source)
    assert child.withdrawn_by is not None
    if (
        value not in bonded.records(saved, bonded.DelegationRelease)
        or (value.actor, value.session, value.outcome) != (parent.actor, child.id, "withdrawn")
        or parent.phase != "withdrawn"
        or bonded.get(saved, parent.id).phase != "withdrawn"
        or child.phase != "withdrawn"
        or am.source(saved, child.id) != child
        or child.withdrawn_event != value.event
        or value.controller != child.controllers[child.withdrawn_by.token]
        or child.effect_event is not None
        or child.completed_event is not None
        or (lesson.used_event is None) != (lesson.released_event == value.event)
        or lesson.used_event is None
        and any(x.source == child.id for x in am.performances(state))
    ):
        raise WorkflowError("Preserve actual withdrawal history; never refund performed work")
    _audit(game, c, value.event, "m3.bonded_am_withdrawn", value.controller, child.id)
