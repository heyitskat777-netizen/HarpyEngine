"""Ended Director contexts identify only their proved physical Handler body."""

import json

import pytest
from test_actors import bindings
from test_actors import canon as canon
from test_actors import ledger as ledger

from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import physical_cell, resolve
from girlframe.engine.m3_director import enter
from girlframe.engine.m3_handler_consequence_state import HandlerArchive, HandlerBody
from girlframe.engine.m3_handler_state import Draft, HandlerPersona


def ended_context(canon):
    state = enter(canon, 1, "director", "actual-presence", ("Afraid", "Defiant"), "source")
    context = state.director_contexts[0]
    old = ActorRef(kind="handler", entity="1", incarnation=context.id)
    state.director_contexts[0] = context.model_copy(
        update={
            "active": False,
            "termination_reason": "director_death",
            "termination_event": "actual-director-death",
        }
    )
    state.facts.append(
        dict(
            kind="recorded_handler_recovery_position",
            actor=old.model_dump_json(),
            cell=json.dumps([4, 4]),
        )
    )
    return state, old


def test_ended_context_keeps_actual_body_position_without_girl_resources_or_new_benefits(canon):
    state, old = ended_context(canon)
    before = state.model_dump_json()
    view = resolve(state, old, bindings(state))
    assert view.rules == "handler" and not view.identities and not view.assets
    assert view.cell == (4, 4)
    current = resolve(state, ActorRef(kind="handler", entity="1"), bindings(state))
    assert current.cell == view.cell
    assert state.model_dump_json() == before


def test_context_never_references_new_same_humans_persona_after_original_death(canon):
    state, old = ended_context(canon)
    original = state.director_contexts[0].body_actor
    assert original is not None
    state.handler_archives.append(
        HandlerArchive(
            id="actual-original-archive",
            actor=original,
            body=HandlerBody(actor=original, tags_json="[]", heat=0),
            source_event="actual-body-death",
            consequence="actual-required-death",
            account="The original physical Handler died",
            appointment="same-appointment",
            links_json="{}",
        )
    )
    state.handler_persona = HandlerPersona(
        id="new-persona",
        owner=1,
        appointment="same-appointment",
        source_event="actual-new-persona",
        draft=Draft(name="New fictional body"),
    )
    with pytest.raises(ValueError, match="old Director context"):
        resolve(state, old, bindings(state))
    view = resolve(
        state, ActorRef(kind="handler", entity="1", incarnation="new-persona"), bindings(state)
    )
    assert view.cell is None and view.rules == "handler"


def test_unproved_legacy_ended_context_cannot_guess_physical_identity(canon):
    state, old = ended_context(canon)
    state.director_contexts[0] = state.director_contexts[0].model_copy(update={"body_actor": None})
    with pytest.raises(ValueError, match="old Director context"):
        resolve(state, old, bindings(state))


def test_active_handler_pose_read_does_not_authorize_stored_body_alias_to_roll(canon):
    state = enter(canon, 1, "director", "actual-presence", ("Afraid", "Defiant"), "source")
    original = state.director_contexts[0].body_actor
    state.facts.append(
        dict(
            kind="recorded_handler_recovery_position",
            actor=original.model_dump_json(),
            cell=json.dumps([2, 4]),
        )
    )
    assert physical_cell(state, original, bindings(state)) == (2, 4)
    with pytest.raises(ValueError, match="actual current Girl-rules context"):
        resolve(state, original, bindings(state))
