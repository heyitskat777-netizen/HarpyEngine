"""Printed Defeat choices change actual original resources and physical state."""

import pytest
from test_actors import bindings
from test_actors import canon as canon
from test_ledger import ledger as ledger

from girlframe.engine import m3_defeat as rules
from girlframe.engine.m2 import AssetState, IdentityState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_defeat_state import Alternative, Decision, NewVoidAsset


def ref(canon, owner=2):
    return ActorRef(
        kind="pilot", entity=str(owner), incarnation=canon.sheets[str(owner)].character_id
    )


def apply(canon, total, options, **values):
    return rules.apply(
        canon,
        ref(canon),
        bindings(canon),
        total,
        Decision(options=options, account="Actual original Defeat consequence", **values),
        "actual-defeat",
        "actual-defeat-choice-event",
        prior_event="actual-defeat-roll-event",
    )


def test_modifier_counts_only_actual_undamaged_girl_assets(canon):
    canon.sheets["2"].heat = 99
    canon.sheets["2"].assets.append(AssetState(id="unrelated-frame", family="frame", name="Frame"))
    girls = [x for x in canon.sheets["2"].assets if x.family == "girl"]
    girls[0].damaged = True
    assert rules.modifier(canon, ref(canon), bindings(canon)) == len(girls) - 1


@pytest.mark.parametrize(
    "total,options",
    [
        (8, ()),
        (8, ("death",)),
        (8, ("escape_cockpit_choose_location", "pilot_rescue_deepen_bond")),
        (11, ("lower_status",)),
        (7, ("death", "lose_frame_choose_later", "change_girl_playbook")),
    ],
)
def test_wrong_tier_and_count_cannot_change_original_state(canon, total, options):
    original = canon.model_dump_json()
    with pytest.raises(ValueError):
        apply(canon, total, options)
    assert canon.model_dump_json() == original


def test_void_recovery_installs_two_actual_void_assets_heat_four_without_repairing_old_ones(canon):
    for asset in canon.sheets["2"].assets:
        asset.damaged = True
    result = apply(
        canon,
        8,
        ("new_girl_and_frame_void_assets_heat4",),
        girl_asset=NewVoidAsset(name="Void lungs", description="Actual Girl alteration"),
        frame_asset=NewVoidAsset(name="Void sail", description="Actual Frame alteration"),
    )
    assert result.state.sheets["2"].heat == 4
    new = [x for x in result.state.sheets["2"].assets if x.id.startswith("actual-defeat:void:")]
    assert len(new) == 2 and all(x.void and not x.damaged for x in new)
    assert all(x.damaged for x in result.state.sheets["2"].assets if x not in new)


def test_escape_changes_actual_occupancy_but_does_not_invent_map_coordinates(canon):
    result = apply(canon, 8, ("escape_cockpit_choose_location",))
    placement = result.state.placements[0]
    assert placement.actor == ref(canon) and placement.mode == "outside_frame"
    assert placement.girl_cell is None and placement.frame_cell is None
    assert (
        result.state.sheets == canon.sheets
        or result.state.sheets["2"].assets == canon.sheets["2"].assets
    )


def test_rescue_deepens_bond_and_records_passenger_without_stealing_assigned_frame(canon):
    result = apply(canon, 8, ("pilot_rescue_deepen_bond",), rescuer=ref(canon, 3))
    body = next(x for x in result.state.placements if x.actor == ref(canon))
    assert body.occupied_frame_owner == ref(canon, 3)
    assert body.frame_instance == "initial:" + str(ref(canon).incarnation)
    assert result.state.bonds["2:3"] == min(canon.bonds.get("2:3", 0) + 1, 2)


def test_injury_is_actual_incapacity_and_waking_requires_later_owned_play_swap(canon):
    result = apply(canon, 8, ("handler_rescue_swap_girl_play_on_waking",))
    assert result.state.sheets["2"].medical_state == "unconscious_injured"
    assert result.state.placements[0].incapacitated
    assert result.followups[0].kind == "medical_wake"


def test_high_rescue_actual_status_and_optional_owned_tag_with_no_forged_gift(canon):
    result = apply(canon, 11, ("lower_status", "another_girl_gives_tag"), tag_giver=ref(canon, 3))
    assert result.state.order != canon.order
    assert result.state.placements[0].custody == ActorRef(kind="handler", entity=str(canon.handler))
    assert result.state.sheets["2"].tags == canon.sheets["2"].tags
    assert result.followups[0].kind == "tag_gift" and result.followups[0].owner == ref(canon, 3)


def test_amnesia_restores_standard_slots_with_one_amnesiac_and_protected_extra(canon):
    sheet = canon.sheets["2"]
    sheet.identities.append(IdentityState(id="protected-extra", name="Protected", protected=True))
    result = apply(canon, 7, ("amnesia_reset_and_replace",), amnesiac_slot=1)
    identities = result.state.sheets["2"].identities
    assert len([x for x in identities if x.name == "Amnesiac"]) == 1
    assert any(x.id == "protected-extra" for x in identities)
    assert len([x for x in identities if not x.protected]) == 4


def test_frame_destruction_records_original_resources_and_defers_free_replacement(canon):
    result = apply(canon, 7, ("lose_frame_choose_later",))
    sheet = result.state.sheets["2"]
    assert sheet.frame_scrapped and not any(x.family == "frame" for x in sheet.assets)
    assert sheet.permissions == canon.sheets["2"].permissions
    assert result.followups[0].kind == "frame_replacement"
    assert result.followups[0].details["next_off_duty"] == "true"


def test_death_and_destroyed_frame_do_not_require_a_dead_girl_to_order_replacement(canon):
    result = apply(canon, 7, ("death", "lose_frame_choose_later"))
    assert [x.kind for x in result.followups] == ["death"]


def test_handler_alternative_defers_all_effects_until_real_offer_and_owner_acceptance(canon):
    result = apply(canon, 7, ("handler_ruinous_alternative", "lose_frame_choose_later"))
    assert result.deferred and result.state == canon
    offer = Alternative(
        account="Actual equally ruinous offer",
        equally_ruinous_confirmed=True,
        assets_removed=(
            next(x.id for x in canon.sheets["2"].assets if not x.void and not x.intrinsic),
        ),
    )
    result = rules.apply(
        canon,
        ref(canon),
        bindings(canon),
        7,
        Decision(
            options=("handler_ruinous_alternative",),
            account="Owner explicitly accepts the actual offer",
        ),
        "actual-defeat",
        "actual-owned-offer-event",
        offer=offer,
    )
    assert len(result.state.sheets["2"].assets) == len(canon.sheets["2"].assets) - 1
