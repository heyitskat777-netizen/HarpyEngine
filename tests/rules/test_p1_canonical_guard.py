"""Unwired final-state comparison: exact independent cost or complete rollback."""

import pytest
from pydantic import Field
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import setup_game, state
from test_shelving_intake import database_rows

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState, spend_heat
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.p1_canonical_projection import (
    HeatSpendScope,
    ProjectionError,
    verify_heat_spend,
)
from girlframe.services.p1_canonical_guard import verify_captured_heat_spend
from girlframe.services.p1_write_capture import capture_writes


def test_captured_independent_heat_cost_rejects_protected_shared_and_sql_side_effects(ledger):
    game, *_ = setup_game(ledger)
    before = state(game)
    # Synthetic available Heat only. This does not claim source/consent admission.
    before.sheets[str(PLAYER.user_id)].heat = 2
    canonical = t.m2["m2_state"]
    with ledger.transaction() as connection:
        connection.execute(
            canonical.update()
            .where(canonical.c.campaign_id == ledger.campaign_id)
            .values(body_json=before.model_dump_json())
        )
    actor, protected = current_ref(before, PLAYER.user_id), current_ref(before, OTHER.user_id)
    scope = HeatSpendScope(actor=actor, amount=1, protected=(protected,))
    after = before.model_copy(deep=True)
    spend_heat(after.sheets[actor.entity], 1)
    after.sheets[actor.entity].revision += 1
    after.revision += 1
    original_rows = database_rows(ledger)

    def compare(candidate, *, sql_side_effect=False, selected_scope=scope):
        with ledger.engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA recursive_triggers=ON")
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                with capture_writes(connection, exclusive_authorizer=True) as capture:
                    connection.execute(
                        canonical.update()
                        .where(canonical.c.campaign_id == ledger.campaign_id)
                        .values(revision=candidate.revision, body_json=candidate.model_dump_json())
                    )
                    if sql_side_effect:
                        connection.execute(
                            t.members.update()
                            .where(
                                t.members.c.campaign_id == ledger.campaign_id,
                                t.members.c.user_id == str(OTHER.user_id),
                            )
                            .values(active=False)
                        )
                    return verify_captured_heat_spend(
                        capture.changes(), ledger.campaign_id, selected_scope
                    )
            finally:
                # Even accepted comparison is deliberately not a production commit.
                connection.rollback()

    evidence = compare(after)
    assert evidence.amount == 1 and evidence.actor == actor
    assert evidence.protected == (protected,) and evidence.authorization is False
    assert evidence.to_revision == before.revision + 1
    assert after.sheets[protected.entity] == before.sheets[protected.entity]
    assert database_rows(ledger) == original_rows

    direct = after.model_copy(deep=True)
    direct.sheets[protected.entity].heat += 1
    with pytest.raises(ProjectionError, match="Unclassified canonical change"):
        compare(direct)
    shared = after.model_copy(deep=True)
    shared.facts.append({"kind": "unclassified_shared", "detail": "PRIVATE_ORIGINAL_CHOICE"})
    with pytest.raises(ProjectionError, match="Unclassified canonical change") as error:
        compare(shared)
    assert "PRIVATE_ORIGINAL_CHOICE" not in str(error.value)
    with pytest.raises(ProjectionError, match="Unclassified SQL write set"):
        compare(after, sql_side_effect=True)
    protected_subject = HeatSpendScope(actor=actor, amount=1, protected=(actor,))
    with pytest.raises(ProjectionError, match="Protected actor"):
        compare(after, selected_scope=protected_subject)
    replaced = after.model_copy(deep=True)
    replaced.sheets[protected.entity].character_id = "unrelated-replacement"
    with pytest.raises(ProjectionError, match="missing or replaced"):
        compare(replaced)
    assert database_rows(ledger) == original_rows


def test_new_canonical_field_requires_explicit_classification(monkeypatch):
    scope = HeatSpendScope(
        actor=ActorRef(kind="pilot", entity="2", incarnation="subject"),
        amount=1,
        protected=(ActorRef(kind="pilot", entity="3", incarnation="protected"),),
    )
    monkeypatch.setitem(GameState.model_fields, "future_unclassified", Field(default=None))
    with pytest.raises(ProjectionError, match="inventory needs classification"):
        verify_heat_spend("{}", "{}", scope)
