import pytest
from test_ledger import PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import setup_game

from girlframe.engine.m2 import AssetState, IdentityState
from girlframe.engine.m3_core import (
    Recovery,
    RepairSelection,
    corrupt,
    damage,
    install,
    recover_off_duty,
    reprogram_labels,
)
from girlframe.engine.m3_economy import RepairQuote, charge_standard, quoted_repair

ledger = ledger_fixture


@pytest.fixture
def sheet(ledger):
    game, *_ = setup_game(ledger)
    from girlframe.engine.m2 import PilotSheet

    return PilotSheet.model_validate_json(__import__("json").dumps(game.sheet(PLAYER)))


@pytest.mark.parametrize(
    "piloting,family,required", [(True, "frame", "defeat"), (False, "girl", "helpless")]
)
def test_last_asset_damage_requires_correct_followup_and_does_not_mutate_input(
    sheet, piloting, family, required
):
    targets = [x for x in sheet.assets if x.family == family]
    for asset in targets[:-1]:
        asset.damaged = True
    result = damage(sheet, targets[-1].id, piloting=piloting)
    assert [x.kind for x in result.followups] == [required]
    assert not targets[-1].damaged
    with pytest.raises(ValueError):
        damage(result.sheet, targets[-1].id, piloting=piloting)


def test_asset_cap_cannot_replace_void_or_erase_unrelated_family(sheet):
    sheet.assets.extend(
        AssetState(id="extra" + str(i), family="girl", name="Extra " + str(i)) for i in range(2)
    )
    incoming = AssetState(id="new", family="girl", name="New")
    with pytest.raises(ValueError):
        install(sheet, incoming)
    void = next(x for x in sheet.assets if x.void)
    with pytest.raises(ValueError):
        install(sheet, incoming, replace=void.id)
    with pytest.raises(ValueError):
        install(sheet, incoming, replace="frame:0")
    result = install(sheet, incoming, replace="extra0")
    assert len([x for x in result.sheet.assets if x.family == "girl"]) == 4
    assert any(x.id == void.id for x in result.sheet.assets)


def test_void_does_not_create_assets_and_mockingbird_threshold_is_special(sheet):
    for asset in sheet.assets:
        if asset.family == "frame" and asset.id != "frame:0":
            asset.void = True
    result = corrupt(sheet, "frame:0", "A human-described alteration", piloting=True)
    assert [x.kind for x in result.followups] == ["mockingbird_resist"]
    assert len(result.sheet.assets) == len(sheet.assets)
    assert not next(x for x in sheet.assets if x.id == "frame:0").void
    with pytest.raises(ValueError):
        corrupt(result.sheet, "frame:0", "Again", piloting=True)
    assert not corrupt(sheet, "frame:0", "Alteration while outside", piloting=False).followups


def test_off_duty_only_unmarks_one_and_preserves_sedation_locks(sheet):
    for identity in sheet.identities:
        identity.marked = True
    for asset in sheet.assets:
        asset.damaged = True
    result = recover_off_duty(sheet, Recovery(unmark_identity="identity:0"))
    assert sum(x.marked for x in result.sheet.identities) == 3
    assert all(not x.damaged for x in result.sheet.assets)
    with pytest.raises(ValueError):
        recover_off_duty(
            sheet, Recovery(unmark_identity="identity:0", sedation_locked=frozenset({"identity:0"}))
        )
    assert all(x.marked for x in sheet.identities)


def test_budget_shortage_repairs_exact_owned_quota_per_family(sheet):
    for asset in sheet.assets:
        asset.damaged = True
    with pytest.raises(ValueError):
        recover_off_duty(sheet, Recovery(repair_limit=1))
    with pytest.raises(ValueError):
        recover_off_duty(
            sheet,
            Recovery(repair_limit=1, repairs=RepairSelection(girl=("frame:0",), frame=("girl:0",))),
        )
    result = recover_off_duty(
        sheet,
        Recovery(repair_limit=1, repairs=RepairSelection(girl=("girl:0",), frame=("frame:0",))),
    )
    assert sum(not x.damaged for x in result.sheet.assets if x.family == "girl") == 1
    assert sum(not x.damaged for x in result.sheet.assets if x.family == "frame") == 1


@pytest.mark.parametrize("girl", ["STIM-BLISSED", "CASUALTY", "OLDGEN", "VATGROWN", "AM"])
def test_reprogramming_fallback_keeps_owner_choice_and_protected_extras(sheet, girl):
    from girlframe.engine.creation_catalog import CATALOG

    sheet.girl = girl
    sheet.identities = [
        IdentityState(id=str(i), name=name) for i, name in enumerate(CATALOG[girl]["identities"])
    ]
    sheet.identities[1].name = "A current Identity"
    sheet.identities.append(IdentityState(id="fixed", name="Fixed extra", protected=True))
    with pytest.raises(ValueError):
        reprogram_labels(sheet, "1")
    labels = reprogram_labels(sheet, "1", CATALOG[girl]["identities"][0])
    assert len(labels) == 5 and "A current Identity" in labels and "Fixed extra" in labels
    with pytest.raises(ValueError):
        reprogram_labels(sheet, "fixed", CATALOG[girl]["identities"][0])


def test_printed_reprogramming_slot_does_not_allow_arbitrary_replacement(sheet):
    sheet.identities[0].name = "Retained"
    assert reprogram_labels(sheet, "identity:0")[1] == "Retained"
    with pytest.raises(ValueError):
        reprogram_labels(sheet, "identity:0", "Dangerous")


@pytest.mark.parametrize(
    "item,cost",
    [
        ("creature_comforts", 1),
        ("privacy", 1),
        ("asset_installment", 1),
        ("visiting_home", 2),
        ("retirement", 20),
        ("ability_unlock", 2),
        ("frame_grafting", 3),
        ("frame_swap", 4),
    ],
)
def test_requisition_costs_are_exact_and_do_not_charge_input(sheet, item, cost):
    sheet.permissions = 20
    result = charge_standard(sheet, item)
    assert result.cost == cost and result.sheet.permissions == 20 - cost and sheet.permissions == 20
    sheet.permissions = 0
    with pytest.raises(ValueError):
        charge_standard(sheet, item)


def test_extra_repair_uses_current_handler_quote_not_an_invented_default(sheet):
    sheet.permissions = 5
    sheet.assets[0].damaged = True
    quote = RepairQuote(
        id="quote",
        handler_id=1,
        owner_id=sheet.owner,
        asset_id=sheet.assets[0].id,
        sheet_revision=sheet.revision,
        quote_revision=2,
        cost=3,
    )
    result = quoted_repair(sheet, quote, current_handler=1, expected_quote_revision=2)
    assert result.sheet.permissions == 2 and not result.sheet.assets[0].damaged
    assert result.provenance == "handler_quote" and sheet.permissions == 5
    with pytest.raises(ValueError):
        quoted_repair(sheet, quote, current_handler=99, expected_quote_revision=2)
    with pytest.raises(ValueError):
        quoted_repair(sheet, quote, current_handler=1, expected_quote_revision=1)
