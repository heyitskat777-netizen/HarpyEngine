"""Actual fictional relationships survive ending without account inheritance."""

import pytest
from test_actors import canon as canon
from test_actors import ledger as ledger

from girlframe.engine import m3_actor_bonds as rules
from girlframe.engine import m3_careers as careers
from girlframe.engine.m2 import TagState, pair_key
from girlframe.engine.m3_actor_state import ActorRef


def refs(canon):
    return rules.current_ref(canon, 2), rules.current_ref(canon, 3)


def test_migration_has_one_authority_and_preserves_npc_not_controller_alias(canon):
    first, second = refs(canon)
    canon.bonds[pair_key(2, 3)] = 2
    npc = canon.world.npcs[0]
    canon.world = canon.world.model_copy(
        update={"npcs": (npc.model_copy(update={"bonds": {"pilot:2": 1}}), *canon.world.npcs[1:])}
    )
    before = canon.model_dump_json()
    result = rules.migrate_actor(canon, first, "conversion-source")
    assert canon.model_dump_json() == before
    assert pair_key(2, 3) not in result.bonds
    assert result.world.npcs[0].bonds == {}
    assert rules.depth(result, first, second) == 2
    assert rules.depth(result, first, ActorRef(kind="npc", entity=npc.id)) == 1
    assert len(result.actor_bonds) == 2
    assert rules.migrate_actor(result, first, "retry").actor_bonds == result.actor_bonds


def test_erasure_tombstone_blocks_legacy_fallback_and_duplicate_authority(canon):
    first, second = refs(canon)
    canon.bonds[pair_key(2, 3)] = 2
    result = rules.set_depth(canon, first, second, 0, "actual-erasure")
    assert rules.depth(result, first, second) == 0 and result.actor_bonds[0].depth == 0
    result.bonds[pair_key(2, 3)] = 1
    with pytest.raises(ValueError, match="numeric authority"):
        rules.depth(result, first, second)


def test_intense_heat_goes_to_actual_two_actors_not_npc_controller(canon):
    first, second = refs(canon)
    result = rules.set_depth(canon, first, second, 2, "actual-bond")
    result = rules.change(result, first, second, 1, "deepening")
    assert result.sheets["2"].heat == canon.sheets["2"].heat + 2
    assert result.sheets["3"].heat == canon.sheets["3"].heat + 2
    npc = ActorRef(kind="npc", entity=canon.world.npcs[0].id)
    result = rules.set_depth(canon, npc, second, 2, "actual-npc-bond")
    result = rules.change(result, npc, second, 1, "npc-deepening")
    assert result.sheets["2"].heat == canon.sheets["2"].heat
    assert result.sheets["3"].heat == canon.sheets["3"].heat + 2


def test_ended_original_bond_and_tag_cannot_be_inherited_by_same_account(canon):
    first, second = refs(canon)
    canon.bonds[pair_key(2, 3)] = 2
    canon.sheets["3"].tags.append(TagState(id="setter-tag", label="Original Tag", giver=2))
    sheet = canon.sheets["2"]
    result = careers.end(
        canon,
        first,
        reason="death",
        source_event="actual-death",
        account="Actual consequence",
        archive_id="actual-archive",
        profile_id=first.incarnation,
        profile_revision=sheet.source_profile_revision,
    )
    assert rules.depth(result, first, second) == 2
    assert careers.tag_giver_ref(result, result.sheets["3"].tags[-1]) == first
    result.sheets["2"] = sheet.model_copy(update={"character_id": "fresh-character"})
    result.order += (2,)
    new = rules.current_ref(result, 2)
    assert new != first and rules.depth(result, new, second) == 0
    result = rules.change(result, first, second, 1, "survivor-deepening")
    assert result.sheets["2"].heat == sheet.heat
    assert result.sheets["3"].heat == canon.sheets["3"].heat + 2


def test_helplessness_tracks_actual_npc_and_has_real_recovery_source(canon):
    first, _ = refs(canon)
    foe = ActorRef(kind="npc", entity=canon.world.npcs[0].id)
    result = rules.make_helpless(canon, first, foe, "last-girl-asset-damaged")
    assert rules.is_helpless(result, first, foe)
    assert not result.sheets["2"].helpless_against
    assert not rules.is_helpless(result, first, rules.current_ref(result, 1))
    result = rules.clear_helpless(result, first, "actual-recovery", foe)
    assert not rules.is_helpless(result, first)
    assert result.helpless_conditions[0].recovery_event == "actual-recovery"
    with pytest.raises(ValueError, match="existing Helplessness"):
        rules.clear_helpless(result, first, "unearned-recovery", foe)


def test_conversion_rebinds_bond_and_helpless_identity_without_controller_alias(canon):
    first, second = refs(canon)
    canon.bonds[pair_key(2, 3)] = 1
    canon.sheets["3"].helpless_against = (2,)
    result = rules.migrate_helpless(
        rules.migrate_actor(canon, first, "conversion"), first, "conversion"
    )
    new = ActorRef(kind="external_pilot", entity="external")
    result = rules.rebind(result, first, new, "actual-conversion")
    assert rules.depth(result, new, second) == 1
    assert rules.depth(result, first, second) == 0
    assert rules.is_helpless(result, second, new)
    assert not result.sheets["3"].helpless_against
    result = rules.set_depth(result, first, second, 2, "separate-old-person-edge")
    with pytest.raises(ValueError, match="merge"):
        rules.rebind(result, first, new, "invalid-merge")


def test_new_tag_givers_are_stamped_without_changing_historical_evidence(canon):
    old = canon.model_copy(deep=True)
    canon.sheets["3"].tags.append(TagState(id="new-tag", label="Source Tag", giver=2))
    result = careers.stamp_tag_givers(old, canon, "actual-new-tag-source")
    tag = result.sheets["3"].tags[-1]
    assert tag.giver_actor == rules.current_ref(result, 2)
    assert tag.giver_character == result.sheets["2"].character_id
    previous = result.model_copy(deep=True)
    tag.giver_actor = rules.current_ref(result, 3)
    with pytest.raises(ValueError, match="setter"):
        careers.stamp_tag_givers(previous, result, "forged-setter-change")


def test_ended_npc_legacy_bond_migrates_without_duplicate_hidden_authority(canon):
    first, _ = refs(canon)
    npc = canon.world.npcs[0]
    canon.world = canon.world.model_copy(
        update={
            "npcs": (
                npc.model_copy(update={"alive": False, "bonds": {"pilot:2": 2}}),
                *canon.world.npcs[1:],
            )
        }
    )
    result = rules.migrate_actor(canon, first, "actual-career-end")
    assert result.world.npcs[0].bonds == {}
    assert rules.depth(result, first, ActorRef(kind="npc", entity=npc.id)) == 2


def test_same_human_handler_and_pilot_have_distinct_typed_bonds_and_ambiguous_legacy_fails(canon):
    from girlframe.engine.m3_handler_consequences import active_handler

    handler = active_handler(canon)
    peer = rules.current_ref(canon, 2)
    canon.sheets["1"] = canon.sheets["2"].model_copy(
        update={"owner": 1, "character_id": "actual-separate-pilot"}
    )
    canon.order = (1, *canon.order)
    pilot = rules.current_ref(canon, 1)
    assert pilot.kind == "pilot" and pilot != handler
    linked = rules.set_depth(canon, handler, peer, 1, "actual-handler-body-source")
    assert rules.depth(linked, handler, peer) == 1 and rules.depth(linked, pilot, peer) == 0
    linked = rules.set_depth(linked, pilot, peer, 2, "actual-separate-pilot-source")
    assert rules.depth(linked, handler, peer) == 1 and rules.depth(linked, pilot, peer) == 2
    ambiguous = canon.model_copy(deep=True)
    ambiguous.bonds["1:2"] = 1
    with pytest.raises(ValueError, match="ambiguous numeric Bond"):
        rules.depth(ambiguous, handler, peer)
    with pytest.raises(ValueError, match="ambiguous numeric Bond"):
        rules.depth(ambiguous, pilot, peer)
