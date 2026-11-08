"""Presence context resources, scoped authority and real departure proofs."""

import pytest
from test_ledger import ledger as ledger_fixture
from test_m2_game import setup_game, state
from test_world import initial

from girlframe.engine import m3_director as rules
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Npc

ledger = ledger_fixture


@pytest.fixture
def canon(ledger):
    game, *_ = setup_game(ledger)
    value = state(game)
    world = initial()
    value.world = update(
        world,
        npcs=tuple(
            Npc(
                id="director" + str(i),
                name="Director " + str(i),
                jobs=("director",),
                controller=i,
                detail="Authority",
                cell=(0, 0),
            )
            for i in (4, 5)
        ),
    )
    value.handler_heat = 9
    return value


def test_printed_context_starts_two_owned_identities_zero_heat_without_pilot_or_status_changes(
    canon,
):
    updated = rules.enter(canon, 1, "director4", "work", ("Afraid", "Defiant"), "source")
    assert canon.handler_heat == 9 and not canon.director_contexts
    assert (
        updated.handler_heat == 0
        and updated.order == canon.order
        and updated.sheets == canon.sheets
    )
    context = updated.director_contexts[0]
    assert context.handler == 1 and len(context.identities) == 2
    assert all(not x.marked and not x.protected and not x.paired for x in context.identities)
    assert "1" not in updated.sheets
    with pytest.raises(ValueError):
        rules.enter(updated, 1, "director4", "work", (), "again")


@pytest.mark.parametrize(
    "labels", [(), ("One",), ("One", "Two", "Three"), (" ", "Two"), ("x" * 121, "Two")]
)
def test_context_rejects_missing_extra_or_invalid_starting_identity_choices(canon, labels):
    with pytest.raises(ValueError):
        rules.enter(canon, 1, "director4", "work", labels, "source")


def test_overlap_and_only_actual_each_director_departure_preserve_resources_until_last_leaves(
    canon,
):
    active = rules.enter(canon, 1, "director4", "work", ("Afraid", "Defiant"), "source")
    active.handler_heat = 7
    active.director_contexts[0].identities[0].marked = True
    original = active.director_contexts[0].identities.copy()
    other = rules.enter(active, 1, "director5", "other-work", (), "overlap")
    assert other.handler_heat == 7 and other.director_contexts[0].identities == original
    identity = other.director_contexts[0].id
    with pytest.raises(ValueError):
        rules.leave(other, 4, identity, "director5", "forged")
    left = rules.leave(other, 4, identity, "director4", "departure4")
    assert left.director_contexts[0].active
    final = rules.leave(left, 5, identity, "director5", "departure5")
    assert not final.director_contexts[0].active and final.handler_heat == 7
    assert final.director_contexts[0].identities == original
    again = rules.enter(final, 1, "director4", "later-work", ("Tired", "Hungry"), "later-visit")
    assert len(again.director_contexts) == 2 and again.handler_heat == 0
    assert again.director_contexts[0] == final.director_contexts[0]
    with pytest.raises(ValueError, match="presence source"):
        rules.enter(final, 1, "director4", "work", ("Again", "Again"), "reused-work")
