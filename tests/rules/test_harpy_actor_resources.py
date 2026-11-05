"""Real converted/native Harpy resources never borrow their human's Pilot sheet."""

import pytest
from test_actors import bindings
from test_actors import canon as canon
from test_actors import ledger as ledger
from test_void import questions

from girlframe.engine import m3_void
from girlframe.engine.m3_actor_resources import Commitment, commit
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_harpy_defeat import harpy, update
from girlframe.engine.m3_harpy_defeat_state import NativeHarpyRuntime
from girlframe.engine.m3_void_state import HarpyAsset, HarpyIdentity


def native(canon):
    state = canon.model_copy(deep=True)
    pilot = state.world.pilots[0].model_copy(
        update={"id": "native-harpy", "kind": "harpy", "controller": 2}
    )
    state.world = state.world.model_copy(update={"pilots": (pilot,)})
    state.native_harpies.append(
        NativeHarpyRuntime(
            id=pilot.id,
            controller=2,
            source_event="actual-setup-review",
            proposed_event="actual-owned-setup",
            world_source_sha256=fingerprint(pilot),
            body_vessel="actual-native-body",
            frame_instance="actual-native-frame",
            cell=pilot.cell,
            frame_cell=pilot.cell,
            linked=True,
            heat=1,
            identities=(HarpyIdentity(id="native-free", name="Free"),),
            tags=(),
        )
    )
    return state, ActorRef(kind="external_pilot", entity=pilot.id)


def converted(canon):
    state, threshold = questions(canon)
    original = state.sheets["2"]
    state = m3_void.rebirth(
        state,
        bindings(state),
        threshold.id,
        "actual-rebirth",
        harpy_id="original-harpy",
        new_vessel="actual-new-body",
        archive_id="original-archive",
        profile_id=threshold.actor.incarnation,
        profile_revision=original.source_profile_revision,
        retained_identities=(),
        new_identities=("Still myself",),
        retained_tags=(),
        retained_plays=(),
        owned_plays=(),
        discarded_bonds=(),
        assets=tuple(
            HarpyAsset(**x.model_dump() | {"description": "Actual new Void Asset", "void": True})
            for x in original.assets
        ),
        account="The original human actually chooses transformation",
    )
    body = state.harpy_states[0]
    state = update(state, ActorRef(kind="external_pilot", entity=body.id), heat=1)
    return state, ActorRef(kind="external_pilot", entity=body.id)


@pytest.mark.parametrize("factory", [native, converted])
def test_mark_and_spend_uses_only_the_actual_harpy_resources_and_source_hash(canon, factory):
    state, actor = factory(canon)
    before = state.model_dump_json()
    profiles = bindings(state)
    view = resolve(state, actor, profiles)
    identity = view.identities[0].id
    result = commit(
        state, actor, profiles, Commitment(heat=2, identity=identity, gain=3), view.source_sha256
    )
    actual = harpy(result.state, actor)
    assert actual.heat == 2 and next(x for x in actual.identities if x.id == identity).marked
    assert state.model_dump_json() == before
    if "2" in state.sheets:
        assert result.state.sheets["2"] == state.sheets["2"]
    assert result.state.world.pilots == state.world.pilots
    assert resolve(result.state, actor, profiles).source_sha256 != view.source_sha256


@pytest.mark.parametrize("factory", [native, converted])
def test_harpy_forced_heat_spend_pair_borrowing_and_stale_commit_fail_before_mutation(
    canon, factory
):
    state, actor = factory(canon)
    state = update(state, actor, heat=5)
    profiles = bindings(state)
    current = resolve(state, actor, profiles)
    encoded = state.model_dump_json()
    for choice in (Commitment(heat=2), Commitment(heat=5, pair_share=2)):
        with pytest.raises(ValueError):
            commit(state, actor, profiles, choice, current.source_sha256)
    assert state.model_dump_json() == encoded
    result = commit(state, actor, profiles, Commitment(heat=5), current.source_sha256)
    assert harpy(result.state, actor).heat == 0
    with pytest.raises(ValueError, match="STALE_RESOURCES"):
        commit(result.state, actor, profiles, Commitment(heat=0), current.source_sha256)


@pytest.mark.parametrize("factory", [native, converted])
def test_real_shutdown_or_incapacity_prevents_piloting_without_moving_or_creating_assets(
    canon, factory
):
    state, actor = factory(canon)
    view = resolve(state, actor, bindings(state))
    assert view.piloting
    state = update(state, actor, frame_shutdown=True)
    changed = resolve(state, actor, bindings(state))
    assert not changed.piloting and changed.inside_frame
    assert changed.cell == view.cell and changed.assets == view.assets
    state = update(state, actor, frame_shutdown=False, body_incapacitated=True)
    assert not resolve(state, actor, bindings(state)).piloting


@pytest.mark.parametrize("factory", [native, converted])
def test_printed_subsumption_preserves_linked_control_without_inventing_mental_incapacity(
    canon, factory
):
    state, actor = factory(canon)
    original = resolve(state, actor, bindings(state))
    state = update(state, actor, subsumed=True, vitals_active=False)
    actual = resolve(state, actor, bindings(state))
    assert actual.piloting and actual.inside_frame
    assert actual.subsumed and actual.vitals_active is False
    assert actual.assets == original.assets and actual.cell == original.cell
