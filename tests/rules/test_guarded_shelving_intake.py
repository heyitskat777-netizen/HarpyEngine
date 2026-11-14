"""Actual private intake source: own result, exact audit/receipt, no hidden side effects."""

import pytest
import sqlalchemy as sa
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import setup_game, state
from test_shelving_intake import database_rows

from girlframe.database import tables as t
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_shelving import KIND, ShelvingService


def test_guarded_withdrawal_rejects_sql_side_effect_and_tampered_event_atomically(
    ledger, monkeypatch
):
    game, _, _, dice = setup_game(ledger)
    intake = ShelvingService(game)
    request = intake.request(PLAYER, "guarded-source-request")
    canonical = state(game)
    baseline = database_rows(ledger)
    actual_event = game.event

    def hidden_write(connection, *args, **kwargs):
        event = actual_event(connection, *args, **kwargs)
        connection.execute(
            t.members.update()
            .where(
                t.members.c.campaign_id == ledger.campaign_id,
                t.members.c.user_id == str(OTHER.user_id),
            )
            .values(active=False)
        )
        return event

    monkeypatch.setattr(game, "event", hidden_write)
    with pytest.raises(WorkflowError, match="INTAKE_SOURCE_REJECTED"):
        intake.change(PLAYER, "guarded-withdraw", request["id"], 1, "withdraw")
    assert database_rows(ledger) == baseline

    def tampered_event(connection, *args, **kwargs):
        kwargs["player_requested"] = False
        return actual_event(connection, *args, **kwargs)

    monkeypatch.setattr(game, "event", tampered_event)
    with pytest.raises(WorkflowError, match="INTAKE_SOURCE_REJECTED"):
        intake.change(PLAYER, "guarded-withdraw", request["id"], 1, "withdraw")
    assert database_rows(ledger) == baseline

    monkeypatch.setattr(game, "event", actual_event)
    result = intake.change(PLAYER, "guarded-withdraw", request["id"], 1, "withdraw")
    assert result["status"] == "withdrawn" and result["player_requested"]
    after = database_rows(ledger)
    assert intake.change(PLAYER, "guarded-withdraw", request["id"], 1, "withdraw") == result
    assert database_rows(ledger) == after
    assert state(game) == canonical and dice.calls == 0
    with ledger.engine.connect() as connection:
        assert (
            connection.scalar(
                sa.select(sa.func.count())
                .select_from(t.events)
                .where(
                    t.events.c.campaign_id == ledger.campaign_id,
                    t.events.c.command_key == "guarded-withdraw",
                    t.events.c.kind == KIND,
                )
            )
            == 1
        )
        assert (
            connection.scalar(
                sa.select(sa.func.count())
                .select_from(t.commands)
                .where(
                    t.commands.c.campaign_id == ledger.campaign_id,
                    t.commands.c.interaction_key == "guarded-withdraw",
                )
            )
            == 1
        )
    # Stored receipts cannot preserve authority after the owner ceases membership.
    with ledger.transaction() as connection:
        connection.execute(
            t.members.update()
            .where(
                t.members.c.campaign_id == ledger.campaign_id,
                t.members.c.user_id == str(PLAYER.user_id),
            )
            .values(active=False)
        )
    unavailable = database_rows(ledger)
    with pytest.raises(WorkflowError, match="Join this campaign"):
        intake.change(PLAYER, "guarded-withdraw", request["id"], 1, "withdraw")
    assert database_rows(ledger) == unavailable
