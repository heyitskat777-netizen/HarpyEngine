import pytest
from pydantic import ValidationError
from test_ledger import ledger as ledger_fixture
from test_m2_game import setup_game, state

from girlframe.discord_adapter.labels import entity_label
from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.m2 import IdentityState, TagState, mark_identity
from girlframe.engine.m3_core import Recovery, recover_off_duty
from girlframe.engine.m3_identity_slots import bind
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_punishments import apply as punish
from girlframe.engine.m3_reprogram import apply

ledger = ledger_fixture


@pytest.fixture
def canon(ledger):
    game, *_ = setup_game(ledger)
    return state(game)


@pytest.mark.parametrize(
    "girl", tuple(key for key, entry in CATALOG.items() if entry["family"] == "girl")
)
def test_reset_uses_actual_starting_set_preserves_protected_cards_and_scoped_slot_locks(
    canon, girl
):
    sheet = canon.sheets["2"]
    sheet.girl = girl
    defaults = CATALOG[girl]["identities"]
    sheet.identities = [
        IdentityState(
            id="old:" + str(i), name=name, paired=name == "Hers", protected=name == "Hers"
        )
        for i, name in enumerate(defaults)
    ]
    ordinary = [x for x in sheet.identities if not x.protected]
    ordinary[0].name = "Retained current label"
    retained = ordinary[0].id
    extra = IdentityState(id="protected", name="A protected extra", protected=True, marked=True)
    sheet.identities.append(extra)
    sheet = bind(sheet)
    locked = next(x for x in sheet.identities if not x.protected and x.id != retained)
    locked.marked = True
    sheet.sedation_locked = (locked.id,)
    sheet.sedation_period = "period"
    paired = next((x for x in sheet.identities if x.paired), None)
    if paired is not None:
        paired.marked = True
    snapshot = sheet.model_dump_json()
    slot = None if "Malfunctioning" in defaults else next(x for x in defaults if x != "Hers")
    result = apply(sheet, retained, slot, "actual-reset", allow_duplicate_labels=True)
    assert sheet.model_dump_json() == snapshot
    assert len(result.identities) == len(defaults) + 1
    assert next(x for x in result.identities if x.id == extra.id) == extra
    if paired is not None:
        assert next(x for x in result.identities if x.paired) == paired
    transferred = next(x for x in result.identities if x.slot == locked.slot)
    assert transferred.marked and transferred.id in result.sedation_locked
    assert any(x.name == "Retained current label" for x in result.identities)
    assert result.revision == sheet.revision + 1
    with pytest.raises(ValueError, match="Sedation"):
        recover_off_duty(result, Recovery(unmark_identity=transferred.id))


def test_retaining_existing_default_label_keeps_two_distinct_markable_cards(canon):
    sheet = bind(canon.sheets["2"])
    current = sheet.identities[0]
    result = apply(sheet, current.id, None, "reset", allow_duplicate_labels=True)
    cards = [x for x in result.identities if x.name == current.name]
    assert len(cards) == 2 and cards[0].id != cards[1].id
    mark_identity(result, cards[0].id, 1)
    assert cards[0].marked and not cards[1].marked
    mark_identity(result, cards[1].id, 1)
    assert result.heat == sheet.heat + 2
    assert entity_label(cards[0].model_dump()) != entity_label(cards[1].model_dump())
    with pytest.raises(ValueError, match="duplicate"):
        apply(sheet, current.id, None, "other-reset", allow_duplicate_labels=False)


def test_correctional_tag_replacement_keeps_sedation_slot_but_explicit_removal_does_not(canon):
    canon.sheets["2"] = bind(canon.sheets["2"])
    original = canon.sheets["2"].identities[0]
    sedated = punish(
        canon,
        2,
        1,
        Details(kind="sedation", identities=("identity:0", "identity:1")),
        entity_id="sedation",
        off_duty=True,
        off_duty_period="period",
    ).state
    sedated.sheets["2"].tags.append(TagState(id="tag", label="Replacement", giver=1))
    replaced = punish(
        sedated,
        2,
        1,
        Details(kind="correctional_programming", identities=(original.id,), embrace_tag="tag"),
        entity_id="replacement",
        off_duty=True,
        off_duty_period="period",
    ).state.sheets["2"]
    new = next(x for x in replaced.identities if x.id == "replacement")
    assert new.slot == original.slot and new.marked
    assert new.id in replaced.sedation_locked and original.id not in replaced.sedation_locked
    removed = punish(
        sedated,
        2,
        1,
        Details(kind="correctional_programming", identities=(original.id,)),
        entity_id="removal",
        off_duty=True,
        off_duty_period="period",
    ).state.sheets["2"]
    assert all(x.id != original.id for x in removed.identities)
    assert original.id not in removed.sedation_locked


def test_slot_binding_adds_no_resource_or_unmark_and_rejects_duplicate_slot_ids(canon):
    sheet = canon.sheets["2"]
    sheet.identities[0].marked = True
    bound = bind(sheet)
    assert [x.name for x in bound.identities] == [x.name for x in sheet.identities]
    assert [x.marked for x in bound.identities] == [x.marked for x in sheet.identities]
    assert bound.heat == sheet.heat and bind(bound) == bound
    data = bound.model_dump(mode="json")
    data["identities"][1]["slot"] = data["identities"][0]["slot"]
    with pytest.raises(ValidationError, match="slots are distinct"):
        type(sheet).model_validate_json(__import__("json").dumps(data))


def test_reset_rejects_forged_retention_protected_slot_and_unscoped_locks(canon):
    sheet = bind(canon.sheets["2"])
    with pytest.raises(ValueError, match="Retain"):
        apply(sheet, "not-owned", None, "reset", allow_duplicate_labels=True)
    sheet.sedation_locked = (sheet.identities[0].id,)
    with pytest.raises(ValueError, match="unscoped"):
        apply(sheet, sheet.identities[0].id, None, "reset", allow_duplicate_labels=True)


def test_m3_tag_embrace_with_matching_label_preserves_distinct_ids_and_policy_ownership(canon):
    sheet = bind(canon.sheets["2"])
    label = sheet.identities[0].name
    sheet.tags.append(TagState(id="tag", label=label, giver=1))
    replaced = sheet.identities[1]
    result = recover_off_duty(
        sheet,
        Recovery(
            embrace_tag="tag",
            replace_identity=replaced.id,
            replacement_id="new-card",
            allow_duplicate_labels=True,
        ),
    ).sheet
    matches = [x for x in result.identities if x.name == label]
    assert len(matches) == 2 and len({x.id for x in matches}) == 2
    assert next(x for x in matches if x.id == "new-card").slot == replaced.slot
    from girlframe.engine.m3_off_duty import RecoveryChoice

    with pytest.raises(ValidationError):
        RecoveryChoice(allow_duplicate_labels=True)
