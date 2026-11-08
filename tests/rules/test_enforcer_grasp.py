"""Actual grasp authority is distinct from roleplay, careers and Helpless recovery."""

import pytest
from test_actors import bindings
from test_actors import canon as canon_fixture
from test_ledger import ledger as ledger_fixture

from girlframe.engine import m3_enforcer as rules
from girlframe.engine.m3_actor_bonds import is_helpless
from girlframe.engine.m3_actor_state import ActorRef

canon, ledger = canon_fixture, ledger_fixture


def ref(state):
    return ActorRef(kind="pilot", entity="2", incarnation=state.sheets["2"].character_id)


@pytest.mark.parametrize(
    "kind,entity,helpless",
    [
        ("npc", "2", True),
        ("pilot", "3", True),
        ("gorgon", "secret", False),
        ("external_pilot", "external", False),
    ],
)
def test_actual_enforcer_grip_holds_other_original_roles_without_granting_false_helplessness(
    canon,
    kind,
    entity,
    helpless,
):
    canon.sheets["2"].frame = "THE ENFORCER"
    target = ActorRef(
        kind=kind,
        entity=entity,
        incarnation=canon.sheets[entity].character_id if kind == "pilot" else None,
    )
    result = rules.grasp(
        canon, ref(canon), target, bindings(canon), "actual-known-action", "actual-effect"
    )
    assert result.enforcer_grasps[0].held
    assert result.enforcer_grasps[0].target == target
    assert is_helpless(result, target, ref(canon)) is helpless
    assert result.placements == canon.placements and result.world == canon.world
    with pytest.raises(ValueError):
        rules.grasp(
            result, ref(canon), target, bindings(result), "duplicate-action", "second-effect"
        )


def test_only_original_holder_can_release_and_open_hand_does_not_cure_helplessness(canon):
    canon.sheets["2"].frame = "THE ENFORCER"
    target = ActorRef(kind="npc", entity="2")
    result = rules.grasp(
        canon, ref(canon), target, bindings(canon), "actual-known-action", "actual-effect"
    )
    with pytest.raises(ValueError):
        rules.release_grasp(result, "actual-effect", target, "escape-source", "No automatic escape")
    released = rules.release_grasp(
        result, "actual-effect", ref(canon), "actual-release", "I open my actual hand"
    )
    assert not released.enforcer_grasps[0].held
    assert is_helpless(released, target, ref(canon))
    ended = rules.end_grasps(result, target, "actual-original-career-ending")
    assert (
        not ended.enforcer_grasps[0].held
        and ended.enforcer_grasps[0].release_event == "actual-original-career-ending"
    )
    assert ended.world == result.world and ended.placements == result.placements
