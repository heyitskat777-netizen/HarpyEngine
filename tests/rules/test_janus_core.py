"""An actual unnamed original Core shares its existing JANUS hardware, never a PC."""

import pytest
from test_actors import bindings
from test_actors import canon as canon
from test_ledger import ledger as ledger

from girlframe.engine import m3_janus as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_harpy_resources import assets, destroy_asset, set_assets
from girlframe.engine.m3_janus_state import CoreFacts
from girlframe.engine.m3_void_state import HarpyAsset, HarpyIdentity


def facts():
    return CoreFacts(
        appearance="Actual still-attached unnamed original ex-Girl",
        heat=3,
        identities=(HarpyIdentity(id="core-id0", name="Original Identity"),),
        girl_assets=(
            HarpyAsset(
                id="core-girl0",
                family="girl",
                name="Actual body",
                description="Existing known original Core body Asset",
                void=True,
            ),
        ),
        exposed=False,
        account="Existing facts confirmed by actual controller",
        facts_confirmed=True,
    )


def admitted(canon):
    canon.sheets["2"].frame = "JANUS-B"
    owner = current_ref(canon, 2)
    instance = "initial:" + str(owner.incarnation)
    changed = rules.admit(
        canon,
        owner,
        instance,
        3,
        facts(),
        identity="actual-core",
        setup="actual-owned-setup",
        proposed_event="actual-controller-proposal",
        event="actual-judge-approval",
        judge=1,
        appointment="actual-appointment",
    )
    return changed, rules.ref(changed.janus_cores[0]), owner


def test_actual_original_controller_distinct_unnamed_core_preserves_frame_and_other_pc(canon):
    previous = GameState.model_validate_json(canon.model_dump_json())
    actual, actor, owner = admitted(canon)
    value = rules.core(actual, actor)
    view = resolve(actual, actor, bindings(actual))
    assert actor != current_ref(actual, 3) and value.controller == 3
    assert view.label == "Harpy Core" and view.frame_instance == "initial:" + owner.incarnation
    assert view.cell is None and view.frame_cell is None
    assert actual.sheets["2"].frame_runtime is previous.sheets["2"].frame_runtime is None
    assert actual.sheets["3"] == previous.sheets["3"]
    assert len(value.tags) == 4 and value.name == "Harpy Core"
    assert not actual.harpy_states and not actual.career_archives
    assert len(actual.sheets) == 2
    with pytest.raises(ValueError):
        rules.admit(
            actual,
            owner,
            value.frame_instance,
            3,
            facts(),
            identity="second-person",
            setup="other-setup",
            proposed_event="other-proposal",
            event="other-review",
            judge=1,
            appointment="actual-appointment",
        )


def test_four_printed_core_tags_are_live_semantics_without_fake_opposing_person(canon):
    actual, actor, _ = admitted(canon)
    assert is_helpless(actual, actor) and not actual.helpless_conditions
    with pytest.raises(ValueError, match="RESTRAINED_CORE"):
        rules.can_act(actual, actor)
    with pytest.raises(ValueError, match="MUZZLED_CORE"):
        rules.can_speak(actual, actor)
    rules.can_speak(actual, actor, mental_link=True)
    value = rules.core(actual, actor)
    removed = rules.update(
        actual,
        actor,
        tags=tuple(
            x
            for x in value.tags
            if x.id not in (value.baseline_tags["drugged"], value.baseline_tags["restrained"])
        ),
    )
    assert not is_helpless(removed, actor)
    rules.can_act(removed, actor)
    with pytest.raises(ValueError, match="MUZZLED_CORE"):
        rules.can_speak(removed, actor)


def test_core_shared_actual_frame_mutation_has_one_origin_and_no_forced_initial_void(canon):
    actual, actor, _ = admitted(canon)
    original = GameState.model_validate_json(actual.model_dump_json())
    union = assets(actual, actor)
    frame = next(x for x in union if x.family == "frame")
    assert not frame.void
    assert not any(x.family == "frame" for x in rules.core(actual, actor).girl_assets)
    updated = set_assets(
        actual,
        actor,
        tuple(x.model_copy(update={"damaged": True}) if x.id == frame.id else x for x in union),
        event="actual-damage",
    )
    assert next(x for x in updated.sheets["2"].assets if x.id == frame.id).damaged
    assert next(x for x in assets(updated, actor) if x.id == frame.id).damaged
    assert updated.sheets["3"] == original.sheets["3"]
    assert rules.core(updated, actor).girl_assets == rules.core(original, actor).girl_assets
    destroyed = destroy_asset(updated, actor, frame.id, event="actual-destruction")
    assert not any(x.id == frame.id for x in destroyed.sheets["2"].assets)
    assert not any(x.id == frame.id for x in assets(destroyed, actor))
    assert len(destroyed.janus_cores) == 1


def test_absent_core_field_does_not_change_old_state_json_or_frame_resources(canon):
    raw = canon.model_dump_json()
    assert '"janus_cores"' not in raw
    assert GameState.model_validate_json(raw).model_dump_json() == raw


def test_detached_unlinked_core_has_no_former_host_frame_authority(canon):
    actual, actor, owner = admitted(canon)
    detached = rules.update(actual, actor, attached=False, linked=False, custody="free")
    assert all(x.family == "girl" for x in assets(detached, actor))
    assert resolve(detached, actor, bindings(detached)).frame_instance is None
    assert detached.sheets[owner.entity] == actual.sheets[owner.entity]
    ordinary = assets(detached, actor)
    changed = set_assets(
        detached,
        actor,
        tuple(x.model_copy(update={"damaged": True}) for x in ordinary),
        event="actual-free-body-damage",
    )
    assert changed.sheets[owner.entity] == actual.sheets[owner.entity]
