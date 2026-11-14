"""Existing canonical event writer rejects early and the enclosing source rolls back."""

import pytest
from test_ledger import PLAYER
from test_ledger import ledger as ledger
from test_m2_game import setup_game, state
from test_shelving_intake import database_rows

from girlframe.database import tables as t
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_enrollment import enroll_current_pilot


def test_enrolled_draining_actor_blocks_canonical_source_without_losing_intake(ledger):
    game, _, _, dice = setup_game(ledger)
    actor = current_ref(state(game), PLAYER.user_id)
    enroll_current_pilot(game, PLAYER, "barrier-enroll", actor)
    with ledger.transaction() as connection:
        connection.execute(
            t.actor_availability.insert().values(
                campaign_id=ledger.campaign_id,
                owner_id=actor.entity,
                incarnation=actor.incarnation,
                generation=2,
                phase="draining",
            )
        )
    before = database_rows(ledger)

    def operation(connection):
        changed = state(game).model_copy(deep=True)
        changed.handler_heat += 1
        game.event(connection, PLAYER.user_id, "blocked-source", "test.canonical", state=changed)
        return {"done": True}

    with pytest.raises(WorkflowError, match="CANONICAL_DRAINING"):
        ledger._write(PLAYER, "blocked-source", "test.canonical", {}, operation)
    assert database_rows(ledger) == before and dice.calls == 0
    # Private intake has no canonical state mutation; still allow withdrawing requests.
    from girlframe.services.p1_shelving import ShelvingService

    intake = ShelvingService(game)
    request = intake.request(PLAYER, "barrier-intake")
    result = intake.change(PLAYER, "barrier-withdraw", request["id"], 1, "withdraw")
    assert result["status"] == "withdrawn"
    assert database_rows(ledger)["m2_state"] == before["m2_state"]
