"""Book PDF 22: exact tiers, actual chooser/target and compulsory effects."""

import pytest
from test_actors import bindings
from test_actors import canon as canon
from test_ledger import ledger as ledger

from girlframe.engine import m3_beneath as rules
from girlframe.engine.m2 import pair_key
from girlframe.engine.m3_actor_state import ActorRef


def ref(state, uid):
    return ActorRef(kind="pilot", entity=str(uid), incarnation=state.sheets[str(uid)].character_id)


def apply(state, level="mid", *, options=("tag", "status"), **details):
    return rules.apply(
        state,
        bindings(state),
        ref(state, 2),
        ref(state, 3),
        level,
        rules.Decision(options=options, text="PRIVATE_ACTUAL_CONFRONTATION", **details),
        "action",
        "choice",
        (1, 2, 3),
    )


@pytest.mark.parametrize(
    "level,options",
    [
        ("mid", ()),
        ("mid", ("tag",)),
        ("mid", ("tag", "pin")),
        ("mid", ("tag", "tag")),
        ("high", ("status", "bond")),
        ("high", ("pin", "punish")),
        ("high", ("tag", "pin", "status")),
        ("low", ("tag", "status")),
        ("low", ("invented",)),
    ],
)
def test_exact_printed_choice_counts_and_lists(level, options):
    with pytest.raises(ValueError):
        rules.choices(level, options)


def test_mid_two_base_effects_lower_only_the_real_victim_and_do_not_spend_again(canon):
    canon.order = (3, 2)
    before = canon.model_dump_json()
    outcome = apply(canon, tag="PRIVATE_INFLECTED_TAG")
    assert canon.model_dump_json() == before
    after = outcome.state
    assert after.order == (2, 3) and not outcome.followups
    assert after.sheets["3"].tags[-1].giver == 2
    assert after.sheets["3"].tags[-1].observers == (1, 2, 3)
    assert after.sheets["2"] == canon.sheets["2"]
    assert after.sheets["3"].permissions == canon.sheets["3"].permissions
    with pytest.raises(ValueError, match="already been applied"):
        apply(after, tag="Cannot repeat the source")


def test_high_performs_base_choice_then_freezes_original_tag_rejection_until_consent(canon):
    outcome = apply(canon, "high", options=("tag", "lock_tag"), tag="Locked Tag", locked_tag="new")
    after = outcome.state
    gate = after.obligations[-1]
    tag = after.sheets["3"].tags[-1]
    assert gate.kind == "tag_rejection_permission" and gate.owner == 2 and gate.target == 3
    assert gate.details["owner_character"] == canon.sheets["2"].character_id
    assert gate.details["target_character"] == canon.sheets["3"].character_id
    assert rules.rejection_blocked(after, 3, tag.id)
    gate.state = "fulfilled"
    assert not rules.rejection_blocked(after, 3, tag.id)


def test_tag_gate_blocks_legacy_missing_character_binding_and_does_not_follow_a_new_character(
    canon,
):
    outcome = apply(canon, "high", options=("tag", "lock_tag"), tag="Locked", locked_tag="new")
    after = outcome.state
    tag = after.sheets["3"].tags[-1]
    after.sheets["3"].character_id = None
    assert rules.rejection_blocked(after, 3, tag.id)
    after.sheets["3"].character_id = "another-original-character"
    assert not rules.rejection_blocked(after, 3, tag.id)


def test_pin_is_an_actual_original_character_fact_and_requires_the_pinned_humans_response(canon):
    outcome = apply(canon, "high", options=("tag", "pin"), tag="Pinned")
    assert outcome.followups[0].kind == "pin_response"
    assert outcome.followups[0].owner == ref(canon, 3)
    pin = next(x for x in outcome.state.facts if x["kind"] == "physical_pin")
    assert pin["target_character"] == canon.sheets["3"].character_id
    assert not outcome.state.sheets["3"].helpless_against
    assert outcome.state.placements == canon.placements


@pytest.mark.parametrize("depth", [1, 2])
def test_weakens_an_actual_bond_with_a_third_character_and_personal_is_erased(canon, depth):
    key = pair_key(3, 1)
    canon.bonds[key] = depth
    outcome = apply(
        canon, options=("tag", "bond"), tag="Insult", bond=ActorRef(kind="handler", entity="1")
    )
    assert outcome.state.bonds.get(key, 0) == depth - 1
    if depth == 1:
        assert key not in outcome.state.bonds
    assert outcome.state.bonds.get(pair_key(2, 3)) == canon.bonds.get(pair_key(2, 3))


def test_weakens_actual_npc_bond_without_fabricating_a_pilot(canon):
    npc = canon.world.npcs[0]
    canon.world = canon.world.model_copy(
        update={
            "npcs": tuple(
                x.model_copy(update={"bonds": {"pilot:3": 2}}) if x.id == npc.id else x
                for x in canon.world.npcs
            )
        }
    )
    outcome = apply(
        canon, options=("tag", "bond"), tag="Insult", bond=ActorRef(kind="npc", entity=npc.id)
    )
    assert next(x for x in outcome.state.world.npcs if x.id == npc.id).bonds["pilot:3"] == 1
    assert outcome.state.sheets.keys() == canon.sheets.keys()


def test_low_counter_reverses_effect_and_chooser_and_requires_real_punishment_authority(canon):
    outcome = apply(canon, "low", options=("tag",), tag="Counter Tag")
    assert outcome.state.sheets["2"].tags[-1].giver == 3
    assert outcome.state.sheets["3"] == canon.sheets["3"]
    canon.order = (2, 3)
    with pytest.raises(ValueError, match="higher Status"):
        apply(canon, "low", options=("punish",))
    authority = rules.Authority(order_id="actual-recorded-order", issuer=1, recipient=ref(canon, 3))
    result = rules.apply(
        canon,
        bindings(canon),
        ref(canon, 2),
        ref(canon, 3),
        "low",
        rules.Decision(options=("punish",), text="Counter under actual orders"),
        "action",
        "choice",
        (1, 2, 3),
        authority=authority,
    )
    assert result.followups[0].owner == ref(canon, 3) and result.followups[0].target == ref(
        canon, 2
    )


@pytest.mark.parametrize(
    "piloting,family,kind", [(False, "girl", "helpless"), (True, "frame", "defeat")]
)
def test_low_last_asset_has_actual_opponent_and_preserves_required_defeat(
    canon, piloting, family, kind
):
    assets = [x for x in canon.sheets["2"].assets if x.family == family]
    for asset in assets[1:]:
        asset.damaged = True
    outcome = rules.apply(
        canon,
        bindings(canon),
        ref(canon, 2),
        ref(canon, 3),
        "low",
        rules.Decision(options=("damage",), asset=assets[0].id, text="Actual counterattack"),
        "action",
        "choice",
        (1, 2, 3),
        actor_piloting=piloting,
    )
    if kind == "helpless":
        assert outcome.state.sheets["2"].helpless_against == (3,)
    else:
        assert outcome.followups[0].kind == "defeat" and outcome.followups[0].owner == ref(canon, 2)


def test_unrelated_details_absent_bonds_unknown_tags_and_wrong_incarnations_fail(canon):
    with pytest.raises(ValueError, match="only the actual details"):
        apply(canon, tag="Tag", asset="unrelated")
    with pytest.raises(ValueError, match="existing actual Bond"):
        canon.bonds.clear()
        apply(canon, options=("tag", "bond"), tag="Tag", bond=ref(canon, 2))
    with pytest.raises(ValueError, match="Tag actually known"):
        apply(canon, "high", options=("status", "lock_tag"), locked_tag="invented")
    with pytest.raises(ValueError, match="STALE_ACTOR"):
        rules.apply(
            canon,
            bindings(canon),
            ref(canon, 2).model_copy(update={"incarnation": "wrong"}),
            ref(canon, 3),
            "mid",
            rules.Decision(options=("tag", "status"), tag="Tag", text="Actual"),
            "action",
            "choice",
            (1, 2, 3),
        )
