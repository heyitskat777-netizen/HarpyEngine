"""Printed WYVERN exception follows actual Asset identity, not its display name."""

import json

import pytest
from pydantic import ValidationError
from test_actors import bindings
from test_ledger import ledger as ledger
from test_m2_game import setup_game, state

from girlframe.engine.m2 import AssetState, PilotSheet
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_assets import can_replace_at_limit, counts_toward_limit, wyvern_intrinsic
from girlframe.engine.m3_core import Recovery, damage, install, recover_off_duty
from girlframe.engine.m3_frame_state import FrameRuntime


@pytest.fixture
def wyvern(ledger):
    game, *_ = setup_game(ledger, frame="WYVERN 0.4")
    return state(game).sheets["2"]


def full(sheet):
    for index in range(3):
        sheet = install(
            sheet, AssetState(id="installed:" + str(index), family="frame", name="Ordinary gear")
        ).sheet
    return sheet


def test_actual_activation_marks_enormous_as_additional_and_five_ordinary_assets_fit(wyvern):
    original = wyvern.model_dump_json()
    extra = next(x for x in wyvern.assets if x.id == "frame:intrinsic:0")
    assert extra.intrinsic == "wyvern_enormous"
    assert not counts_toward_limit(wyvern, extra) and not can_replace_at_limit(wyvern, extra)
    result = full(wyvern)
    frame = [x for x in result.assets if x.family == "frame"]
    assert len(frame) == 6 and sum(counts_toward_limit(result, x) for x in frame) == 5
    assert wyvern.model_dump_json() == original
    assert any(x.id == extra.id for x in result.assets)


def test_at_actual_limit_replace_an_ordinary_non_void_asset_but_never_enormous(wyvern):
    sheet = full(wyvern)
    new = AssetState(id="new", family="frame", name="New gear")
    before = sheet.model_dump_json()
    with pytest.raises(ValueError, match="non-Void"):
        install(sheet, new, replace="frame:intrinsic:0")
    with pytest.raises(ValueError, match="non-Void"):
        install(sheet, new)
    assert sheet.model_dump_json() == before
    result = install(sheet, new, replace="frame:0").sheet
    assert len([x for x in result.assets if x.family == "frame"]) == 6
    assert any(x.id == "frame:intrinsic:0" for x in result.assets)
    assert not any(x.id == "frame:0" for x in result.assets)


def test_custom_asset_called_enormous_gets_no_intrinsic_properties(wyvern):
    fake = AssetState(id="custom", family="frame", name="Enormous")
    sheet = install(wyvern, fake).sheet
    assert not wyvern_intrinsic(sheet, fake)
    assert counts_toward_limit(sheet, fake) and can_replace_at_limit(sheet, fake)
    assert sum(counts_toward_limit(sheet, x) for x in sheet.assets if x.family == "frame") == 3
    for index in range(2):
        sheet = install(
            sheet, AssetState(id="more:" + str(index), family="frame", name="Gear")
        ).sheet
    result = install(
        sheet, AssetState(id="replacement", family="frame", name="Replacement"), replace="custom"
    ).sheet
    assert any(x.id == "frame:intrinsic:0" for x in result.assets)
    assert not any(x.id == "custom" for x in result.assets)


def test_legacy_initial_intrinsic_uses_original_id_and_creation_proof_without_rewriting_source(
    wyvern,
):
    payload = wyvern.model_dump(mode="json")
    for asset in payload["assets"]:
        del asset["intrinsic"]
    legacy = PilotSheet.model_validate_json(json.dumps(payload))
    extra = next(x for x in legacy.assets if x.id == "frame:intrinsic:0")
    assert extra.intrinsic is None and wyvern_intrinsic(legacy, extra)
    extra.name = "A renamed original Asset"
    assert wyvern_intrinsic(legacy, extra)
    result = full(legacy)
    assert len([x for x in result.assets if x.family == "frame"]) == 6
    assert extra.intrinsic is None


def test_additional_asset_still_takes_damage_repairs_and_counts_for_actual_defeat(wyvern):
    sheet = full(wyvern)
    ordinary = [x for x in sheet.assets if x.family == "frame" and counts_toward_limit(sheet, x)]
    for asset in ordinary:
        result = damage(sheet, asset.id, piloting=True)
        assert not result.followups
        sheet = result.sheet
    last = damage(sheet, "frame:intrinsic:0", piloting=True)
    assert [x.kind for x in last.followups] == ["defeat"]
    repaired = recover_off_duty(last.sheet, Recovery()).sheet
    assert all(not x.damaged for x in repaired.assets)
    assert not counts_toward_limit(
        repaired, next(x for x in repaired.assets if x.id == "frame:intrinsic:0")
    )


def test_descriptor_exposes_cap_properties_only_for_actual_pilot_rules(ledger):
    game, *_ = setup_game(ledger, frame="WYVERN 0.4")
    canon = state(game)
    ref = ActorRef(kind="pilot", entity="2", incarnation=canon.sheets["2"].character_id)
    actor = resolve(canon, ref, bindings(canon))
    extra = next(x for x in actor.assets if x.id == "frame:intrinsic:0")
    assert extra.counts_toward_limit is False and extra.can_replace_at_limit is False
    assert all(x.counts_toward_limit is True for x in actor.assets if x.id != extra.id)


def test_frame_intrinsic_marker_cannot_be_forged_on_a_girl_asset():
    with pytest.raises(ValidationError, match="belongs to its Frame"):
        AssetState(id="fake", family="girl", name="Enormous", intrinsic="wyvern_enormous")


def test_legacy_replacement_intrinsic_uses_actual_frame_identity_not_a_lookalike(wyvern):
    sheet = wyvern.model_copy(deep=True)
    sheet.frame_runtime = FrameRuntime(id="new-frame", generation=1, source_work="owned-request")
    original = next(x for x in sheet.assets if x.intrinsic)
    original.id, original.intrinsic = "new-frame:intrinsic", None
    assert wyvern_intrinsic(sheet, original)
    lookalike = AssetState(id="frame:intrinsic:0", family="frame", name="Enormous")
    sheet.assets.append(lookalike)
    assert not wyvern_intrinsic(sheet, lookalike)
