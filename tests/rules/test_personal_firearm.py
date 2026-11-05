"""Actual unlock/graft eligibility, source review gate, pistol identity and loss recovery."""

import json

import pytest
from test_actors import bindings
from test_actors import canon as canon_fixture
from test_ledger import ledger as ledger_fixture

from girlframe.engine import m3_personal_firearm as rules
from girlframe.engine.m2 import AssetState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_frame_state import FrameRuntime
from girlframe.engine.rules_registry import Registry
from girlframe.services.m3_access import load_registry

canon, ledger = canon_fixture, ledger_fixture


def reviewed_registry(*, approved=True):
    # Deliberately synthetic source-review provenance; never modifies the public registry.
    data = load_registry().model_dump(mode="json")
    entry = next(x for x in data["entries"] if x["id"] == rules.RULE)
    entry.update(
        implementation="implemented",
        source_audit="audited",
        independent_review="approved" if approved else "pending",
        reviewer="SYNTHETIC TEST REGISTRY ONLY" if approved else None,
        review_reference="fixture, not actual independent review" if approved else None,
        test_evidence=["tests/rules/test_personal_firearm.py"],
        contract=dict(
            trigger="Acquire Personal Firearm or lose its actual issued pistol before ordinary8+.",
            actor_type="Actual original Girl and her current Frame.",
            pre_roll_sources=["Original held grant and lost item before roll."],
            roll_kind="diceless",
            allowed_modifiers=[],
            tier_options={
                "acquisition": ["Issue pistol."],
                "return": ["Actual ordinary8+ permits owned retrieval."],
            },
            choice_ownership="Owner chooses acquisition, cap replacement and optional return.",
            target_policy="Own original Girl and current usable Frame only.",
            post_roll_effects=[
                "Charge2/3, issue actual Girl Asset; later lost-pistol return is free."
            ],
            mandatory_followups=[],
            handler_or_gm_intervention="Source review remains required; no extra approval or roll.",
            test_fixture_ids=["tests/rules/test_personal_firearm.py"],
        ),
    )
    return Registry.model_validate_json(json.dumps(data))


def actor(canon):
    return ActorRef(kind="pilot", entity="2", incarnation=canon.sheets["2"].character_id)


def buy(canon, *, kind="frame_grafting", registry=None, replace=None):
    ref = actor(canon)
    return rules.purchase(
        canon,
        ref,
        bindings(canon),
        resolve(canon, ref, bindings(canon)).source_sha256,
        registry or reviewed_registry(),
        kind,
        "Actual acquisition",
        "actual-paid-source",
        "actual-grant",
        "actual-event",
        replace=replace,
    )


@pytest.mark.parametrize(
    "kind,frame,price", [("ability_unlock", "THE ENFORCER", 2), ("frame_grafting", "JANUS-B", 3)]
)
def test_actual_source_price_and_frame_eligibility_install_one_girl_pistol(
    canon, kind, frame, price
):
    canon.sheets["2"].frame = frame
    canon.sheets["2"].permissions = 5
    result = buy(canon, kind=kind)
    assert result.sheets["2"].permissions == 5 - price
    assert len(result.personal_firearms) == 1
    issue = result.personal_firearms[0].issues[0]
    assert next(x for x in result.sheets["2"].assets if x.id == issue.asset).family == "girl"
    assert canon.sheets["2"].permissions == 5
    with pytest.raises(ValueError, match="already recorded|already holds"):
        buy(result, kind=kind)


def test_wrong_donor_or_unreviewed_rule_cannot_charge_or_grant(canon):
    canon.sheets["2"].permissions = 5
    before = canon.model_dump_json()
    with pytest.raises(ValueError, match="implementation and review"):
        buy(canon, registry=reviewed_registry(approved=False))
    with pytest.raises(ValueError, match="your actual Frame"):
        buy(canon, kind="ability_unlock")
    assert canon.model_dump_json() == before


def test_girl_cap_requires_actual_ordinary_replacement_and_preserves_void(canon):
    canon.sheets["2"].permissions = 5
    sheet = canon.sheets["2"]
    next(x for x in sheet.assets if x.family == "girl").void = True
    while len([x for x in sheet.assets if x.family == "girl"]) < 4:
        sheet.assets.append(
            AssetState(
                id="extra-girl-asset-" + str(len(sheet.assets)),
                family="girl",
                name="Ordinary extra",
            )
        )
    with pytest.raises(ValueError, match="cap"):
        buy(canon)
    protected = next(x for x in sheet.assets if x.family == "girl" and x.void)
    with pytest.raises(ValueError, match="cap"):
        buy(canon, replace=protected.id)
    ordinary = next(x for x in sheet.assets if x.family == "girl" and not x.void)
    result = buy(canon, replace=ordinary.id)
    assert any(x.id == protected.id for x in result.sheets["2"].assets)
    assert not any(x.id == ordinary.id for x in result.sheets["2"].assets)


def test_damage_is_not_loss_and_each_real_loss_return_has_a_distinct_item_identity(canon):
    canon.sheets["2"].permissions = 5
    purchased = buy(canon)
    entitlement = purchased.personal_firearms[0]
    original = entitlement.issues[0].asset
    firearm = next(x for x in purchased.sheets["2"].assets if x.id == original)
    firearm.damaged = True
    with pytest.raises(ValueError, match="still-lost"):
        rules.reissue(
            purchased,
            actor(purchased),
            bindings(purchased),
            entitlement.id,
            original,
            entitlement.frame_instance,
            "actual-return",
            "actual-roll",
        )
    purchased.sheets["2"].assets.remove(firearm)
    restored = rules.reissue(
        purchased,
        actor(purchased),
        bindings(purchased),
        entitlement.id,
        original,
        entitlement.frame_instance,
        "actual-return",
        "actual-roll",
    )
    returned = restored.personal_firearms[0].issues[-1].asset
    assert (
        returned != original
        and restored.sheets["2"].permissions == purchased.sheets["2"].permissions
    )
    assert sum(x.id == returned for x in restored.sheets["2"].assets) == 1
    restored.sheets["2"].assets = [x for x in restored.sheets["2"].assets if x.id != returned]
    with pytest.raises(ValueError, match="still-lost"):
        rules.reissue(
            restored,
            actor(restored),
            bindings(restored),
            entitlement.id,
            returned,
            entitlement.frame_instance,
            "same-roll-duplicate",
            "actual-roll",
        )
    again = rules.reissue(
        restored,
        actor(restored),
        bindings(restored),
        entitlement.id,
        returned,
        entitlement.frame_instance,
        "later-real-return",
        "later-real-roll",
    )
    assert len(again.personal_firearms[0].issues) == 3


def test_retaining_selected_rule_in_a_new_frame_preserves_existing_pistol_without_duplicate(canon):
    canon.sheets["2"].permissions = 5
    original = buy(canon)
    entitlement = original.personal_firearms[0]
    assets = original.sheets["2"].assets[:]
    original.sheets["2"].frame_runtime = FrameRuntime(
        id="actual-next-frame",
        generation=2,
        source_work="actual-swap",
        acquired_rules=(rules.RULE,),
    )
    kept = rules.retain(
        original,
        actor(original),
        bindings(original),
        entitlement.id,
        "actual-next-frame",
        "actual-retained-source",
    )
    assert kept.sheets["2"].assets == assets
    assert kept.personal_firearms[0].frame_instance == "actual-next-frame"
    replacement_actor = ActorRef(kind="pilot", entity="2", incarnation="new-character")
    assert not rules.held(kept, replacement_actor, "actual-next-frame")
