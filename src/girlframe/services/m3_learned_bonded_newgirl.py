"""Finite learned Bonded delegation to the original Pair's actual Newgirl session."""

import json
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_bonded as bonded
from girlframe.engine import m3_newgirl_sex as newgirl
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_learned_play_state import LearnedSexLink, put_learned_sex_link
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def parent_lesson(state: GameState, child: newgirl.Session) -> str | None:
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
        or json.loads(row.payload_json).get("session") != child
    ):
        raise WorkflowError("Recover this exact original Newgirl source and human author")


def _child(
    game: "GameService", c: Connection, state: GameState, parent: bonded.Source
) -> newgirl.Session:
    links = [x for x in bonded.records(state, bonded.Delegation) if x.source == parent.id]
    if len(links) != 1:
        raise WorkflowError("Recover the one original Pair Newgirl child")
    link = links[0]
    birth = _history(c, game, link.event)
    original_link = next(
        (x for x in bonded.records(birth, bonded.Delegation) if x.id == link.id), None
    )
    child = newgirl.get(state, link.session)
    original = newgirl.get(birth, child.id)
    from girlframe.services.m3_dose_up import _native

    people = [_native(game, c, birth, ref) for ref in (child.actor, *child.partners)]
    if (
        parent.route != "delegated"
        or parent.delegated_rule != newgirl.RULE
        or parent.changeling_source is not None
        or parent.action is not None
        or parent.effect_event is not None
        or original_link is None
        or any(
            getattr(link, x) != getattr(original_link, x)
            for x in ("id", "source", "session", "rule", "actor", "target", "event")
        )
        or (link.actor, link.target, link.rule) != (parent.actor, parent.target, newgirl.RULE)
        or child.actor != parent.actor
        or not child.partners
        or child.partners[0] != parent.target
        or len(set((child.actor, *child.partners))) != len(child.partners) + 1
        or child.bonded_source != parent.id
        or child.controllers != {x.ref.token: x.controller for x in people}
        or child.vessels != {x.ref.token: x.vessel_id for x in people}
        or any(child.controllers.get(k) != v for k, v in parent.controllers.items())
        or any(child.vessels.get(k) != v for k, v in parent.vessels.items())
        or any(
            not any(r.actor == x.ref and r.controller == x.controller for r in parent.cast.roles)
            for x in people
        )
        or child.cast != parent.cast
        or child.learned_source is not None
        or child.changeling_source is not None
        or child.proposed_event != link.event
        or any(
            getattr(child, x) != getattr(original, x)
            for x in (
                "id",
                "actor",
                "partners",
                "controllers",
                "vessels",
                "cast",
                "registry",
                "proposed_event",
                "proposal",
                "bonded_source",
                "learned_source",
                "changeling_source",
                "mentors_before",
                "mentor_source",
            )
        )
        or original.phase != "invited"
        or original.action is not None
        or original.bound_event is not None
        or original.effect_event is not None
        or original.completed_event is not None
        or any(x.session == child.id for x in newgirl.records(birth, newgirl.Consent))
    ):
        raise WorkflowError("Preserve this original Pair rule, independent people and source birth")
    _audit(
        game, c, child.proposed_event, "m3.newgirl_sex_proposed", int(child.actor.entity), child.id
    )
    return child


def _answer(
    game: "GameService", c: Connection, state: GameState, child: newgirl.Session, accepted: bool
) -> newgirl.Consent:
    values = [x for x in newgirl.records(state, newgirl.Consent) if x.session == child.id]
    if (
        not values
        or len({x.person for x in values}) != len(values)
        or any(x.person not in child.partners for x in values)
        or (
            accepted
            and (
                {x.person for x in values} != set(child.partners)
                or not all(x.accepted for x in values)
            )
        )
        or (not accepted and len([x for x in values if not x.accepted]) != 1)
    ):
        raise WorkflowError("Recover every original participant's independent child answer")
    decisive = None
    for value in values:
        saved = _history(c, game, value.event)
        answered = newgirl.get(saved, child.id)
        saved_answers = [
            x for x in newgirl.records(saved, newgirl.Consent) if x.session == child.id
        ]
        expected = (
            "declined"
            if not value.accepted
            else "accepted"
            if {x.person for x in saved_answers if x.accepted} == set(child.partners)
            else "invited"
        )
        if (
            value.controller != child.controllers.get(value.person.token)
            or not value.account.strip()
            or value not in saved_answers
            or answered.phase != expected
            or answered.action is not None
            or answered.bound_event is not None
            or any(x not in values for x in saved_answers)
            or any(not x.accepted and x != value for x in saved_answers)
            or any(
                getattr(answered, name) != getattr(child, name)
                for name in (
                    "actor",
                    "partners",
                    "controllers",
                    "vessels",
                    "cast",
                    "proposed_event",
                    "bonded_source",
                    "learned_source",
                    "changeling_source",
                )
            )
        ):
            raise WorkflowError("Preserve each child's separately authored original answer")
        _audit(game, c, value.event, "m3.newgirl_sex_confirmed", value.controller, child.id)
        if expected == ("accepted" if accepted else "declined"):
            decisive = value
    if decisive is None:
        raise WorkflowError("Recover the actual final acceptance or independent refusal")
    return decisive


def binding_child(
    game: "GameService",
    c: Connection,
    state: GameState,
    parent: bonded.Source,
    lesson: LearnedSexLink,
) -> newgirl.Session:
    child = _child(game, c, state, parent)
    if (
        parent.learned_source != lesson.id
        or lesson.rule_id != bonded.SEX
        or lesson.session != parent.id
        or (lesson.actor, lesson.target) != (child.actor, child.partners[0])
        or child.action is None
        or child.bound_event is None
    ):
        raise WorkflowError("Bind only the exact accepted parent lesson and original Newgirl child")
    _answer(game, c, state, child, True)
    action = game.action(c, child.action)
    meta = action["data"].get(newgirl.PLAY, {})
    if (
        str(action["actor_id"]) != child.actor.entity
        or action["scene_id"] != child.cast.id
        or int(action["channel_id"]) != child.cast.channel
        or action["data"].get("play") != newgirl.PLAY
        or action["data"].get("prepared", {}).get("source_work") != child.id
        or meta.get("session") != child.id
        or meta.get("bonded_source") != parent.id
        or meta.get("bonded_lesson") != lesson.id
        or meta.get("learned_source") is not None
        or meta.get("changeling_source") is not None
        or meta.get("actor") != child.actor.model_dump(mode="json")
        or meta.get("partners") != [x.model_dump(mode="json") for x in child.partners]
        or meta.get("cast") != child.cast.model_dump(mode="json")
    ):
        raise WorkflowError("Reserve the parent lesson only for this actual child's one Action")
    return child


def _unused(
    game: "GameService", c: Connection, state: GameState, parent: bonded.Source
) -> newgirl.Session:
    child = _child(game, c, state, parent)
    link = next(x for x in bonded.records(state, bonded.Delegation) if x.source == parent.id)
    actions = t.m2["m2_actions"]
    if (
        child.action is not None
        or child.bound_event is not None
        or child.effect_event is not None
        or child.completed_event is not None
        or link.action is not None
        or link.completed_event is not None
        or parent.completed_event is not None
        or c.scalar(
            sa.select(actions.c.id).where(
                actions.c.campaign_id == game.store.campaign_id,
                sa.or_(
                    sa.func.json_extract(actions.c.body_json, "$.prepared.source_work") == child.id,
                    sa.func.json_extract(actions.c.body_json, "$.newgirl_sex.session") == child.id,
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

    value = newgirl.get(state, identity)
    parent = prove(game, c, state, value.bonded_source or "")
    child = _unused(game, c, state, parent)
    if parent.phase != "bound" or child.phase not in ("declined", "withdrawn"):
        raise WorkflowError("Release only the actual unused declined or withdrawn Newgirl child")
    if child.phase == "declined":
        answers = [
            x
            for x in newgirl.records(state, newgirl.Consent)
            if x.session == child.id and not x.accepted
        ]
        if (
            len(answers) != 1
            or answers[0].event != event
            or answers[0].person not in child.partners
            or answers[0].controller != owner
            or child.controllers.get(answers[0].person.token) != owner
        ):
            raise WorkflowError("Release only the actual participant's own pending refusal event")
    elif owner != int(child.actor.entity):
        raise WorkflowError("Only the original owner withdraws the unused child")
    lesson = get(state, parent.learned_source) if parent.learned_source else None
    if lesson is not None and (
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
            outcome=child.phase,
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
            raise WorkflowError("Recover the original Newgirl child release evidence")
        return
    if len(releases) != 1:
        raise WorkflowError("Preserve the one original delegated release")
    value = releases[0]
    child = _unused(game, c, state, parent)
    saved = _history(c, game, value.event)
    ended = newgirl.get(saved, child.id)
    if (
        value not in bonded.records(saved, bonded.DelegationRelease)
        or (value.actor, value.session, value.outcome) != (parent.actor, child.id, parent.phase)
        or child.phase != value.outcome
        or ended.phase != value.outcome
        or bonded.get(saved, parent.id).phase != value.outcome
        or value.controller
        != (
            _answer(game, c, state, child, False).controller
            if value.outcome == "declined"
            else int(child.actor.entity)
        )
    ):
        raise WorkflowError("Preserve this original human's exact no-effect child release")
    if value.outcome == "declined" and _answer(game, c, state, child, False).event != value.event:
        raise WorkflowError("Preserve the original counterpart's own refusal")
    _audit(
        game,
        c,
        value.event,
        "m3.newgirl_sex_" + ("confirmed" if value.outcome == "declined" else "withdrawn"),
        value.controller,
        child.id,
    )


def released_parent(
    game: "GameService", c: Connection, state: GameState, child: newgirl.Session
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
