"""Actual source assets, distinct bodies and no invented NPC/Handler hit points."""

import pytest
from test_actors import bindings
from test_actors import canon as canon
from test_actors import ledger as ledger
from test_physical_operations import place, ref

from girlframe.engine import m3_battle as rules
from girlframe.engine.m3_actor_state import ActorRef


def test_actual_last_frame_asset_requires_original_defeat_without_damage_to_girl(canon):
    state = place(canon)
    actor = ref(state, 2)
    frame = [x for x in state.sheets["2"].assets if x.family == "frame"]
    for asset in frame[:-1]:
        asset.damaged = True
    before = state.model_dump_json()
    changed, needed = rules.damage(
        state, actor, frame[-1].id, bindings(state), "real-damage", opponent=ref(state, 3)
    )
    assert state.model_dump_json() == before
    assert needed[0].kind == "defeat" and needed[0].target == actor
    assert all(x.damaged for x in changed.sheets["2"].assets if x.family == "frame")
    assert [x for x in changed.sheets["2"].assets if x.family == "girl"] == [
        x for x in state.sheets["2"].assets if x.family == "girl"
    ]


def test_last_girl_outside_requires_real_opponent_then_makes_helpless(canon):
    state = place(canon, mode="outside_frame")
    actor = ref(state, 2)
    girl = [x for x in state.sheets["2"].assets if x.family == "girl"]
    for asset in girl[:-1]:
        asset.damaged = True
    with pytest.raises(ValueError, match="actual opponent"):
        rules.damage(state, actor, girl[-1].id, bindings(state), "no-foe")
    changed, needed = rules.damage(
        state, actor, girl[-1].id, bindings(state), "real-foe", opponent=ref(state, 3)
    )
    assert not needed
    assert changed.helpless_conditions[-1].subject == actor
    assert changed.helpless_conditions[-1].foe == ref(state, 3)


def test_outside_combat_cannot_invent_frame_weapon_or_unknown_occupancy(canon):
    frame = next(x for x in canon.sheets["2"].assets if x.family == "frame")
    with pytest.raises(ValueError, match="cockpit state"):
        rules.owned_asset(canon, ref(canon, 2), frame.id, bindings(canon), attacking=True)
    state = place(canon, mode="outside_frame")
    with pytest.raises(ValueError, match="Girl Assets"):
        rules.owned_asset(state, ref(state, 2), frame.id, bindings(state), attacking=True)


def test_ordinary_handler_gear_is_not_a_hit_point_counter(canon):
    actor = ActorRef(kind="handler", entity=str(canon.handler))
    assert rules.category(canon, actor) == "handler"
    assert not rules.intact_assets(canon, actor, bindings(canon))
    changed, needed = rules.damage(canon, actor, None, bindings(canon), "real-handler-damage")
    assert needed[0].kind == "handler_damage"
    assert changed.handler_archives == canon.handler_archives


def test_unknown_original_cannot_redirect_damage_to_successor(canon):
    old = ref(canon, 2)
    canon.sheets["2"].character_id = "replacement"
    with pytest.raises(ValueError, match="current Pilot"):
        rules.category(canon, old)


def test_core_modifier_counts_actual_body_and_current_linked_frame_not_remote_assigned_assets(
    canon,
):
    state = place(canon, mode="piloting")
    actor = ref(state, 2)
    assert len(rules.intact_assets(state, actor, bindings(state))) == len(state.sheets["2"].assets)
    from girlframe.engine.m3_physical import cockpit_exit

    outside = cockpit_exit(
        state, bindings(state), actor, "actual-exit-for-strike", "I leave the actual cockpit"
    )
    assert {x.family for x in rules.intact_assets(outside, actor, bindings(outside))} == {"girl"}
    assert outside.sheets == state.sheets


def test_passenger_has_own_girl_resources_and_actual_carrier_core_gate(canon):
    from girlframe.engine.m3_physical import rescue_to_cockpit

    state = place(place(canon, 2, mode="outside_frame"), 3)
    guest, carrier = ref(state, 2), ref(state, 3)
    state = rescue_to_cockpit(
        state,
        bindings(state),
        guest,
        carrier,
        "actual-carrier-rescue",
        "I pull the actual original Girl into my cockpit",
    )
    assert all(x.family == "girl" for x in rules.intact_assets(state, guest, bindings(state)))
    with pytest.raises(ValueError, match="Expose"):
        rules.core_available(state, guest, carrier, bindings(state))
    state = rules.expose_frame(
        state,
        carrier,
        bindings(state),
        "actual-carrier-open",
        "I open my actual Frame Core",
        willing=True,
    )
    assert rules.core_available(state, guest, carrier, bindings(state)) == "actual-carrier-open"


def test_frame_exposure_uses_two_real_conditions_and_does_not_invent_empty_resources(canon):
    state = place(canon)
    actor, foe = ref(state, 2), ref(state, 3)
    with pytest.raises(ValueError, match="two actual source conditions"):
        rules.expose_frame(
            state, actor, bindings(state), "fake-expose", "Only one imagined weakness", opponent=foe
        )
    for asset in state.sheets["2"].assets:
        if asset.family == "girl":
            asset.damaged = True
    for identity in state.sheets["2"].identities:
        identity.marked = True
    changed = rules.expose_frame(
        state,
        actor,
        bindings(state),
        "actual-two-conditions",
        "Actual weakened Girl body and all actual marked Identities",
        opponent=foe,
    )
    assert rules.core_available(changed, actor, foe, bindings(changed)) == "actual-two-conditions"
    state.sheets["2"].assets = [x for x in state.sheets["2"].assets if x.family != "girl"]
    state.sheets["2"].identities = []
    with pytest.raises(ValueError, match="two actual source conditions"):
        rules.expose_frame(
            state,
            actor,
            bindings(state),
            "empty-not-weakness",
            "No fabricated conditions",
            opponent=foe,
        )
