"""v39 actual withdrawal plus v40 owned savepoints, without new source authority."""

import pytest
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import setup_game, state
from test_shelving_intake import database_rows

from girlframe.database import tables as t
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_shelving import ShelvingService
from girlframe.services.p1_write_capture import source_savepoint


def test_actual_withdrawal_owned_savepoint_rollback_and_retained_write_guard(ledger, monkeypatch):
    game, _, _, dice = setup_game(ledger)
    intake = ShelvingService(game)
    request = intake.request(PLAYER, "combined-request")
    baseline = database_rows(ledger)
    canonical = state(game)
    original_event = game.event
    retain_hidden_write = True

    def event_in_owned_step(connection, *args, **kwargs):
        with source_savepoint(connection):
            with pytest.raises(ValueError, match="discard scratch"):
                with source_savepoint(connection):
                    connection.execute(
                        t.members.update()
                        .where(
                            t.members.c.campaign_id == ledger.campaign_id,
                            t.members.c.user_id == str(OTHER.user_id),
                        )
                        .values(active=False)
                    )
                    raise ValueError("discard scratch")
            event = original_event(connection, *args, **kwargs)
            if retain_hidden_write:
                connection.execute(
                    t.members.update()
                    .where(
                        t.members.c.campaign_id == ledger.campaign_id,
                        t.members.c.user_id == str(OTHER.user_id),
                    )
                    .values(active=False)
                )
            return event

    monkeypatch.setattr(game, "event", event_in_owned_step)
    with pytest.raises(WorkflowError, match="INTAKE_SOURCE_REJECTED"):
        intake.change(PLAYER, "combined-withdraw", request["id"], 1, "withdraw")
    assert database_rows(ledger) == baseline

    # Identical key remains usable after atomic rejection. Only discarded scratch
    # writes disappear from evidence; a released hidden write above was rejected.
    retain_hidden_write = False
    result = intake.change(PLAYER, "combined-withdraw", request["id"], 1, "withdraw")
    assert result["status"] == "withdrawn"
    after = database_rows(ledger)
    assert after != baseline
    assert intake.change(PLAYER, "combined-withdraw", request["id"], 1, "withdraw") == result
    assert database_rows(ledger) == after
    assert state(game) == canonical and dice.calls == 0
