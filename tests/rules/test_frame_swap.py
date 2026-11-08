"""Synthetic-review-only exchange candidate; never certifies destination rule runtimes."""

import json

import pytest
from test_actors import bindings
from test_actors import canon as canon_fixture
from test_ledger import ledger as ledger_fixture
from test_personal_firearm import buy, reviewed_registry

from girlframe.engine import m3_frame_swap as rules
from girlframe.engine.creation import AssetChoice, official_frame
from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.fanbase import Fanbase
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_frame_swap_state import Selection
from girlframe.engine.m3_personal_firearm import RULE, held
from girlframe.engine.rules_registry import Registry

canon, ledger = canon_fixture, ledger_fixture
DESTINATIONS = (
    "THE PRINCE",
    "CONSUME",
    "JANUS-B",
    "DOCTORDOCTOR MK. II",
    "WYVERN 0.4",
    "THE ENFORCER",
    "CHANGELING",
    "PROJECT ANKOU",
    "THE RED QUEEN",
)


def synthetic_registry():
    data = reviewed_registry().model_dump(mode="json")
    # The positive fixture tests exchange state ONLY, not unimplemented destination mechanics.
    contract = next(x["contract"] for x in data["entries"] if x["id"] == RULE)
    for entry in data["entries"]:
        if entry.get("scope") == "frame" and entry.get("frame_rule") == "base":
            entry.update(
                implementation="implemented",
                source_audit="audited",
                independent_review="approved",
                reviewer="SYNTHETIC EXCHANGE TEST ONLY",
                review_reference="Synthetic exchange only; destination consumers untested",
                contract=contract,
                test_evidence=["tests/rules/test_frame_swap.py"],
            )
    return Registry.model_validate_json(json.dumps(data))


def actor(state, uid=2):
    return ActorRef(kind="pilot", entity=str(uid), incarnation=state.sheets[str(uid)].character_id)


def selection(state, frame="THE ENFORCER"):
    names = CATALOG[official_frame(frame)]["assets"][:2]
    return Selection(
        frame=frame,
        name="Actual selected new Frame",
        appearance="New hardware",
        assets=tuple(AssetChoice(name=x, description="Actual " + x) for x in names),
        retained_asset=next(x.id for x in state.sheets["2"].assets if x.family == "frame"),
        retained_rule=RULE,
        account="PRIVATE_EXCHANGE_ACCOUNT",
        fanbase=Fanbase(
            demographics=("Young boys", "Older men"),
            demanded=("Sexy", "Kind"),
            rejected=("Dangerous", "Girly"),
        )
        if frame == "THE PRINCE"
        else None,
        court_role="The Knight" if frame == "THE RED QUEEN" else None,
        court_target=actor(state, 3) if frame == "THE RED QUEEN" else None,
        psych_strings=rules.bonded_refs(state, actor(state)) if frame == "CHANGELING" else (),
    )


def prepared(canon, frame="THE ENFORCER"):
    canon.sheets["2"].frame = "THE ENFORCER" if frame == "JANUS-B" else "JANUS-B"
    canon.sheets["2"].permissions = 10
    return buy(canon, kind="ability_unlock" if frame == "JANUS-B" else "frame_grafting")


@pytest.mark.parametrize("frame", DESTINATIONS)
def test_candidate_exchanges_actual_baseline_keeps_girl_and_one_old_item_rule_without_free_pistol(
    canon,
    frame,
):
    original = prepared(canon, frame)
    pick, registry = selection(original, frame), synthetic_registry()
    kept = next(x for x in original.sheets["2"].assets if x.id == pick.retained_asset)
    kept.damaged = kept.void = True
    before = original.model_dump_json()
    result = rules.purchase(
        original,
        actor(original),
        bindings(original),
        resolve(original, actor(original), bindings(original)).source_sha256,
        registry,
        pick,
        "actual-exchange",
        "actual-swap-source",
        "actual-owned-plan",
        court_accepted=frame == "THE RED QUEEN",
    )
    assert original.model_dump_json() == before
    sheet = result.sheets["2"]
    assert sheet.permissions == original.sheets["2"].permissions - 4
    assert sheet.frame == frame and not sheet.frame_scrapped
    assert sheet.frame_runtime.acquired_rules == (RULE,)
    assert sheet.character_id == original.sheets["2"].character_id
    assert [x for x in sheet.assets if x.family == "girl"] == [
        x for x in original.sheets["2"].assets if x.family == "girl"
    ]
    assert next(x for x in sheet.assets if x.id == kept.id).damaged
    assert next(x for x in sheet.assets if x.id == kept.id).void
    assert len([x for x in sheet.assets if x.family == "frame"]) == (
        4 if frame == "WYVERN 0.4" else 3
    )
    assert (
        held(result, actor(result), sheet.frame_runtime.id)[0].issues
        == original.personal_firearms[0].issues
    )
    assert result.bonds == original.bonds and result.placements == original.placements
    if frame == "JANUS-B":
        assert len(sheet.frame_runtime.harpy_core.tags) == 4
    elif frame == "CONSUME":
        assert sheet.frame_runtime.consume_hunger == "Quiet"
    elif frame == "THE RED QUEEN":
        assert sheet.frame_runtime.court["The Knight"] == 3
    elif frame == "CHANGELING":
        assert sheet.frame_runtime.psych_string_refs == pick.psych_strings


def test_real_unimplemented_destination_gate_does_not_debit_or_claim_complete_baseline(canon):
    original = prepared(canon)
    before = original.model_dump_json()
    with pytest.raises(ValueError, match="implementation and review"):
        rules.purchase(
            original,
            actor(original),
            bindings(original),
            resolve(original, actor(original), bindings(original)).source_sha256,
            reviewed_registry(),
            selection(original),
            "actual-exchange",
            "actual-source",
            "actual-plan",
        )
    assert original.model_dump_json() == before


def test_no_repeat_same_playbook_or_missing_actual_court_consent(canon):
    original = prepared(canon)
    for pick in (selection(original, "JANUS-B"), selection(original, "THE RED QUEEN")):
        with pytest.raises(ValueError, match="different|accept"):
            rules.purchase(
                original,
                actor(original),
                bindings(original),
                resolve(original, actor(original), bindings(original)).source_sha256,
                synthetic_registry(),
                pick,
                "actual-exchange",
                "actual-source",
                "actual-plan",
            )
