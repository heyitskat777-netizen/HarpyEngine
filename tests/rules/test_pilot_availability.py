"""Trusted synthetic enrollment only; production transitions remain unavailable."""

import pytest
import sqlalchemy as sa
from test_ledger import PLAYER
from test_ledger import ledger as ledger
from test_m2_game import setup_game, state

from girlframe.database import tables as t
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_availability import require_current_active


def test_current_pilot_epoch_missing_active_draining_and_immutable(ledger):
    game, _, _, dice = setup_game(ledger)
    before = state(game)
    actor = current_ref(before, PLAYER.user_id)
    values = dict(
        campaign_id=ledger.campaign_id,
        owner_id=actor.entity,
        incarnation=actor.incarnation,
        generation=1,
        phase="active",
    )
    with ledger.transaction() as connection:
        with pytest.raises(WorkflowError, match="ACTOR_UNAVAILABLE"):
            require_current_active(connection, game, PLAYER, 1)
        # Test fixture only: deliberately no enrollment API is exposed.
        connection.execute(t.actor_availability.insert().values(**values))
        assert require_current_active(connection, game, PLAYER, 1).actor == actor
        with pytest.raises(WorkflowError, match="AVAILABILITY_STALE"):
            require_current_active(connection, game, PLAYER, 2)
        connection.execute(
            t.actor_availability.insert().values(**dict(values, generation=2, phase="draining"))
        )
        with pytest.raises(WorkflowError, match="ACTOR_UNAVAILABLE"):
            require_current_active(connection, game, PLAYER, 1)
        for sql in (
            t.actor_availability.update().values(phase="active"),
            t.actor_availability.delete(),
            t.actor_availability.insert().prefix_with("OR REPLACE").values(**values),
            t.actor_availability.insert().values(**dict(values, generation=3)),
            t.actor_availability.insert().values(**dict(values, generation=3, phase="frozen")),
        ):
            with pytest.raises(sa.exc.IntegrityError):
                connection.execute(sql)
        assert connection.scalar(sa.select(sa.func.count()).select_from(t.actor_availability)) == 2
    with ledger.transaction() as connection:
        with pytest.raises(WorkflowError, match="ACTOR_UNAVAILABLE"):
            require_current_active(connection, game, PLAYER, 1)
    assert state(game) == before and dice.calls == 0
