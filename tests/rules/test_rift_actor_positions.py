"""Actual reviewed offstage travel masks cached positions without copying resources."""

import pytest
from test_actors import bindings
from test_actors import canon as canon
from test_actors import ledger as ledger

from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import frame_position, physical_cell, resolve
from girlframe.engine.m3_harpy_defeat_state import Travel


@pytest.mark.parametrize(
    "kind,entity",
    [
        ("pilot", "2"),
        ("external_pilot", "external"),
        ("npc", "2"),
        ("gorgon", "secret"),
    ],
)
def test_actual_offstage_body_hides_cached_cell_preserves_resources_and_changes_source_hash(
    canon, kind, entity
):
    actor = ActorRef(
        kind=kind,
        entity=entity,
        incarnation=canon.sheets["2"].character_id if kind == "pilot" else None,
    )
    original = resolve(canon, actor, bindings(canon))
    before_sheets, before_world = canon.model_copy(deep=True).sheets, canon.world
    travels_frame = kind in ("pilot", "external_pilot")
    canon.harpy_travels.append(
        Travel(
            id="actual-reviewed-crossing",
            actor=actor,
            controller=original.controller,
            source_event="actual-owned-route",
            source_sha256=original.source_sha256,
            rift="actual-source-rift",
            frame_instance=original.frame_instance,
            travels_frame=travels_frame,
            destination=None,
            account="The real actor crosses this actual Rift",
            navigation="Actual passage facts; no grid-scale assumption",
            judge=1,
            appointment="actual-gm-appointment",
            state="offstage",
            response_event="actual-gm-route-reviewed",
            review="The real GM verifies this passage",
        )
    )
    after = resolve(canon, actor, bindings(canon))
    assert after.cell is None and after.offstage_source == "actual-reviewed-crossing"
    assert physical_cell(canon, actor, bindings(canon)) is None
    assert after.assets == original.assets and after.identities == original.identities
    assert after.heat == original.heat and after.controller == original.controller
    assert after.source_sha256 != original.source_sha256
    assert canon.sheets == before_sheets and canon.world == before_world
    if travels_frame:
        assert frame_position(canon, actor, original.frame_instance, fallback=(9, 9)) is None
    if kind == "pilot":
        different = ActorRef(kind="pilot", entity="3", incarnation=canon.sheets["3"].character_id)
        assert frame_position(canon, different, original.frame_instance, fallback=(9, 9)) == (9, 9)


def test_a_proposed_route_does_not_move_a_body_and_wrong_controller_does_not_take_it(canon):
    actor = ActorRef(kind="npc", entity="2")
    original = resolve(canon, actor, bindings(canon))
    proposed = Travel(
        id="proposed-route",
        actor=actor,
        controller=original.controller,
        source_event="owned-proposal",
        source_sha256=original.source_sha256,
        rift="actual-source-rift",
        travels_frame=False,
        destination=None,
        account="A proposed future crossing",
        navigation="Actual route facts",
        judge=1,
        appointment="actual-gm-appointment",
    )
    canon.harpy_travels.append(proposed)
    assert resolve(canon, actor, bindings(canon)) == original
    canon.harpy_travels[-1] = proposed.model_copy(update={"state": "offstage", "controller": 3})
    with pytest.raises(ValueError, match="inconsistent real travel sources"):
        resolve(canon, actor, bindings(canon))


def test_unknown_guardian_preserves_known_hold_until_actual_offstage_movement(canon):
    from test_void import threshold

    from girlframe.engine.m3_void import prevent_entry

    state, source = threshold(canon, inside=False)
    guardian = ActorRef(kind="pilot", entity="3", incarnation=state.sheets["3"].character_id)
    state = prevent_entry(
        state,
        bindings(state),
        source.id,
        guardian,
        "actual-owned-physical-hold",
        "The real guardian holds her at the established location",
    )
    assert resolve(state, guardian, bindings(state)).cell is None
    assert resolve(state, source.actor, bindings(state)).cell == (0, 0)
    view = resolve(state, guardian, bindings(state))
    state.harpy_travels.append(
        Travel(
            id="actual-reviewed-guardian-crossing",
            actor=guardian,
            controller=3,
            source_event="actual-owned-crossing",
            source_sha256=view.source_sha256,
            rift="actual-source-rift",
            travels_frame=False,
            destination=None,
            account="The guardian actually leaves with the held body",
            navigation="Actual physical source for crossing",
            judge=1,
            appointment="actual-gm-appointment",
            state="offstage",
            response_event="actual-guardian-crossing-review",
            review="Actual reviewed movement",
        )
    )
    assert resolve(state, source.actor, bindings(state)).cell is None
