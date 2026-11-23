"""Role-bound campaigns expose the native training limitation without extra writes."""

from types import SimpleNamespace

import pytest

from director_trial import campaign_training
from girlframe.database import tables
from girlframe.services.onboarding import WorkflowError
from test_ledger import ADMIN, OTHER, PLAYER, count
from test_ledger import ledger as ledger_fixture

ledger = ledger_fixture


def test_campaign_training_accepts_actual_members_and_keeps_their_identity(ledger):
    ledger.join(ADMIN, "training-handler-member")
    ledger.join(PLAYER, "training-pilot-member")
    terminal = campaign_training(SimpleNamespace(store=ledger), ADMIN)
    events = count(ledger, tables.events)
    pilot = terminal.view(PLAYER)
    handler = terminal.view(ADMIN)
    assert pilot["training_available"] is False
    assert pilot["status"]["phase"] == "unavailable"
    assert pilot["availability_code"] == "NATIVE_REHEARSAL_REQUIRED"
    assert pilot["speaker"] == "pilot" and not pilot["facilitator"]
    assert handler["speaker"] == "handler" and handler["facilitator"]
    assert not {"participants", "own_consent", "work", "contributions"} & pilot.keys()
    with pytest.raises(WorkflowError, match="Join this campaign"):
        terminal.view(OTHER)
    with pytest.raises(WorkflowError, match="NATIVE_REHEARSAL_REQUIRED"):
        terminal.perform(
            PLAYER, "unavailable-consent", {"operation": "consent", "consent": True}
        )
    assert count(ledger, tables.events) == events
