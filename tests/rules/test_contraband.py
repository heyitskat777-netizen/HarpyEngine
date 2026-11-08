"""Pure optional acquisition, actual resource caps and concealed-Asset properties."""

import json

import pytest
from pydantic import ValidationError
from test_contraband_service import ready
from test_ledger import ledger as ledger_fixture
from test_m2_game import state

from girlframe.engine import m3_contraband as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_core import Recovery, damage, recover_off_duty
from girlframe.engine.m3_requisition_state import GirlAsset
from girlframe.services.m3_actors import profiles

ledger = ledger_fixture


@pytest.fixture
def actual(ledger):
    _, _, game, _, _ = ready(ledger, public=True)
    with ledger.engine.connect() as c:
        bindings = profiles(c, ledger.campaign_id)
    return state(game), bindings


def claim(original, bindings, **values):
    find = original.contraband_finds[0]
    actor = resolve(original, find.actor, bindings)
    options = dict(
        taken=True,
        choice=GirlAsset(name="Actual item", description="An ordinary item"),
        account="Actual historical find",
        response_event="actual-owner-response",
    )
    options.update(values)
    return rules.claim(original, bindings, find, actor.source_sha256, **options)


def test_pure_actual_find_grants_only_an_ordinary_concealed_girl_asset_and_preserves_input(actual):
    original, bindings = actual
    before = original.model_dump_json()
    after = claim(original, bindings)
    assert original.model_dump_json() == before
    assert len(after.sheets["2"].assets) == len(original.sheets["2"].assets) + 1
    asset = after.sheets["2"].assets[-1]
    assert asset.family == "girl" and asset.concealed and not asset.void and not asset.damaged
    assert after.sheets["3"] == original.sheets["3"] and after.bonds == original.bonds
    assert after.sheets["2"].permissions == original.sheets["2"].permissions
    assert after.sheets["2"].identities == original.sheets["2"].identities
    assert after.placements == original.placements
    with pytest.raises(ValueError):
        claim(after, bindings)


def test_decline_does_not_add_repair_spend_or_move_anything(actual):
    original, bindings = actual
    after = claim(original, bindings, taken=False, choice=None, account="")
    assert after.sheets == original.sheets and after.world == original.world
    assert after.placements == original.placements and after.bonds == original.bonds
    assert after.contraband_finds[0].taken is False
    assert after.contraband_finds[0].response_event != original.contraband_finds[0].source_event


@pytest.mark.parametrize(
    "values",
    (
        {"choice": None},
        {"account": " "},
        {"taken": False},
        {"choice": GirlAsset(name=" ", description="Not a name")},
        {"choice": GirlAsset(name="Item", description=" ")},
    ),
)
def test_invalid_or_unrelated_claim_details_do_not_change_original_state(actual, values):
    original, bindings = actual
    before = original.model_dump_json()
    with pytest.raises(ValueError):
        claim(original, bindings, **values)
    assert original.model_dump_json() == before


def test_concealed_asset_takes_damage_and_repairs_normally_without_becoming_public(actual):
    original, bindings = actual
    after = claim(original, bindings)
    sheet = after.sheets["2"]
    girl_assets = [x for x in sheet.assets if x.family == "girl"]
    for asset in girl_assets[:-1]:
        result = damage(sheet, asset.id, piloting=False)
        assert not result.followups
        sheet = result.sheet
    result = damage(sheet, girl_assets[-1].id, piloting=False)
    assert [x.kind for x in result.followups] == ["helpless"]
    repaired = recover_off_duty(result.sheet, Recovery()).sheet
    assert repaired.assets[-1].concealed and not repaired.assets[-1].damaged


def test_pure_publication_is_explicit_owned_and_does_not_mutate_original_claim(actual):
    original, bindings = actual
    claimed = claim(original, bindings)
    find = claimed.contraband_finds[0]
    actor = resolve(claimed, find.actor, bindings)
    before = claimed.model_dump_json()
    shared = rules.share(claimed, bindings, find, actor.source_sha256)
    assert claimed.model_dump_json() == before and claimed.sheets["2"].assets[-1].concealed
    assert not shared.sheets["2"].assets[-1].concealed
    assert shared.contraband_finds == claimed.contraband_finds
    assert shared.sheets["2"].heat == claimed.sheets["2"].heat
    assert fingerprint(claimed.contraband_finds[0]) == fingerprint(shared.contraband_finds[0])


def test_legacy_json_defaults_to_no_finds_or_concealed_assets_without_inventing_a_draw(actual):
    original, _ = actual
    body = original.model_dump(mode="json")
    del body["contraband_finds"]
    for sheet in body["sheets"].values():
        for asset in sheet["assets"]:
            del asset["concealed"]
    legacy = GameState.model_validate_json(json.dumps(body))
    assert legacy.contraband_finds == []
    assert all(not x.concealed for s in legacy.sheets.values() for x in s.assets)


def test_original_find_model_rejects_invented_decisions_and_half_grants(actual):
    original, _ = actual
    find = original.contraband_finds[0]
    for changes in (
        {"index": True},
        {"index": -1},
        {"index": 2},
        {"asset_id": "invented"},
        {"taken": True, "response_event": "answer"},
        {"taken": False},
        {"population": [find.actor.model_dump(mode="json")] * 2},
    ):
        body = json.loads(find.model_dump_json())
        body.update(changes)
        with pytest.raises(ValidationError):
            type(find).model_validate_json(json.dumps(body))
