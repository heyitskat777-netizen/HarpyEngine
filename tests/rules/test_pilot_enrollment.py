"""Actual guarded enrollment of the authenticated original Pilot, never shelving."""

import pytest
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import setup_game, state
from test_shelving_intake import database_rows

from girlframe.database import tables as t
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_availability import require_current_active
from girlframe.services.p1_enrollment import enroll_current_pilot


def test_authenticated_enrollment_atomic_side_effect_replay_and_no_resume(ledger, monkeypatch):
    game, _, _, dice = setup_game(ledger)
    canonical = state(game)
    actor = current_ref(canonical, PLAYER.user_id)
    other = current_ref(canonical, OTHER.user_id)
    before = database_rows(ledger)
    with pytest.raises(WorkflowError, match="ENROLLMENT_STALE"):
        enroll_current_pilot(game, PLAYER, "enroll", other)
    assert database_rows(ledger) == before
    actual_event = game.event

    def hidden_write(connection, *args, **kwargs):
        result = actual_event(connection, *args, **kwargs)
        connection.execute(
            t.members.update()
            .where(
                t.members.c.campaign_id == ledger.campaign_id,
                t.members.c.user_id == str(OTHER.user_id),
            )
            .values(active=False)
        )
        return result

    monkeypatch.setattr(game, "event", hidden_write)
    with pytest.raises(WorkflowError, match="ENROLLMENT_REJECTED"):
        enroll_current_pilot(game, PLAYER, "enroll", actor)
    assert database_rows(ledger) == before
    monkeypatch.setattr(game, "event", actual_event)
    result = enroll_current_pilot(game, PLAYER, "enroll", actor)
    assert result["original_actor"] == actor.model_dump(mode="json")
    assert result["phase"] == "active" and result["generation"] == 1
    saved = database_rows(ledger)
    assert len(saved["p1_actor_availability"]) == 1
    assert len(saved["events"]) == len(before["events"]) + 1
    assert enroll_current_pilot(game, PLAYER, "enroll", actor) == result
    assert database_rows(ledger) == saved
    assert enroll_current_pilot(game, PLAYER, "enroll-again", actor) == result
    duplicate = database_rows(ledger)
    assert duplicate["events"] == saved["events"]
    assert duplicate["p1_actor_availability"] == saved["p1_actor_availability"]
    with ledger.transaction() as connection:
        epoch = require_current_active(connection, game, PLAYER, 1)
        assert epoch.actor == actor and epoch.generation == 1
        # Synthetic drain fixture only; enrollment must not become a resume API.
        connection.execute(
            t.actor_availability.insert().values(
                campaign_id=ledger.campaign_id,
                owner_id=actor.entity,
                incarnation=actor.incarnation,
                generation=2,
                phase="draining",
            )
        )
    draining = database_rows(ledger)
    for key in ("enroll", "enroll-after-drain"):
        with pytest.raises(WorkflowError, match="ACTOR_UNAVAILABLE"):
            enroll_current_pilot(game, PLAYER, key, actor)
        assert database_rows(ledger) == draining
    assert state(game) == canonical and dice.calls == 0
