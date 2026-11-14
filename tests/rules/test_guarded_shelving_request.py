"""Guard actual request/proposal/confirmation without changing actor availability."""

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import setup_game, state
from test_shelving_intake import database_rows

from girlframe.database import tables as t
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import FacilitatorService
from girlframe.services.p1_shelving import ShelvingService


def test_guarded_request_proposal_confirmation_and_atomic_rejection(ledger, monkeypatch):
    game, _, _, dice = setup_game(ledger)
    facilitator = FacilitatorService(game)
    facilitator.configure(ADMIN, "guard-request-gm", "user", ADMIN.user_id)
    service = ShelvingService(game)
    canonical = state(game)
    baseline = database_rows(ledger)
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
    with pytest.raises(WorkflowError, match="INTAKE_SOURCE_REJECTED"):
        service.request(ADMIN, "guard-proposal", PLAYER.user_id)
    assert database_rows(ledger) == baseline
    monkeypatch.setattr(game, "event", actual_event)
    proposal = service.request(ADMIN, "guard-proposal", PLAYER.user_id)
    assert not proposal["player_requested"]
    after_proposal = database_rows(ledger)
    assert service.request(ADMIN, "guard-proposal", PLAYER.user_id) == proposal
    assert database_rows(ledger) == after_proposal

    def tampered_event(connection, *args, **kwargs):
        kwargs["player_requested"] = False
        return actual_event(connection, *args, **kwargs)

    monkeypatch.setattr(game, "event", tampered_event)
    with pytest.raises(WorkflowError, match="INTAKE_SOURCE_REJECTED"):
        service.request(PLAYER, "guard-confirm")
    assert database_rows(ledger) == after_proposal
    monkeypatch.setattr(game, "event", actual_event)
    confirmed = service.request(PLAYER, "guard-confirm")
    assert confirmed["player_requested"] and confirmed["revision"] == 2
    assert confirmed["initiator"] == ADMIN.user_id
    assert confirmed["configuration_event"] == proposal["configuration_event"]
    assert confirmed["original_actor"] == proposal["original_actor"]
    saved = database_rows(ledger)
    assert service.request(PLAYER, "guard-confirm") == confirmed
    assert database_rows(ledger) == saved
    assert service.request(PLAYER, "guard-duplicate") == confirmed
    duplicate = database_rows(ledger)
    assert duplicate["events"] == saved["events"]
    assert duplicate["campaigns"] == saved["campaigns"]
    assert len(duplicate["commands_inbox"]) == len(saved["commands_inbox"]) + 1
    assert state(game) == canonical and dice.calls == 0

    facilitator.configure(ADMIN, "guard-replace-gm", "user", OTHER.user_id)
    changed = database_rows(ledger)
    with pytest.raises(WorkflowError, match="currently configured human facilitator"):
        service.request(ADMIN, "guard-proposal", PLAYER.user_id)
    assert database_rows(ledger) == changed
