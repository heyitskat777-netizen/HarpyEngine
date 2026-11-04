"""Actual Observation tiers, owners, mechanical consequences and bounded recovery."""

import pytest
from test_ledger import ledger as ledger_fixture
from test_m2_game import setup_game, state
from test_off_duty import active

from girlframe.engine import m3_observation as rules
from girlframe.engine.m2 import AssetState
from girlframe.engine.m3_core import Recovery
from girlframe.engine.m3_observation_state import Details
from girlframe.engine.m3_off_duty import Period, acknowledge_scene, ordinary_roll, recovery

ledger = ledger_fixture


@pytest.fixture
def canon(ledger):
    game, *_ = setup_game(ledger)
    return state(game)


def ordered(canon, *, hiding=True):
    return rules.order(
        active(canon), 2, 1, 2, canon, hiding, "Actual Handler suspicion", "order-event"
    )


def rolled(canon, faces=(4, 4), *, hiding=True):
    period, canon = ordered(canon, hiding=hiding)
    lowered = rules.lower_before_roll(period, 2, canon)
    return rules.roll(period, period.revision, 2, lowered, faces), lowered


def test_handler_order_preserves_input_and_blocks_ordinary_substitution(canon):
    original = canon.model_copy(deep=True)
    period, canon = ordered(canon)
    assert original.obligations == [] and active(original).progress == {}
    assert canon.obligations[0].kind == "void_observation"
    assert period.progress["2"].observation.source_event == "order-event"
    with pytest.raises(ValueError, match="Void Observation"):
        ordinary_roll(period, period.revision, 2, canon, (1, 1))
    with pytest.raises(ValueError, match="Only the current Handler"):
        rules.order(active(canon), 2, 3, 2, canon, False, "Forgery", "fake")
    with pytest.raises(ValueError, match="before"):
        rules.order(period, period.revision, 1, 2, canon, False, "Second order", "another")


@pytest.mark.parametrize("faces,handler_count", [((1, 1), 0), ((4, 4), 1), ((6, 6), 2)])
def test_actual_void_count_and_tier_counts_are_not_heat_or_status(canon, faces, handler_count):
    canon.sheets["2"].heat = 300
    period, canon = rolled(canon, faces)
    assert canon.order == (3, 2)
    roll = period.progress["2"].roll
    assert roll.modifier == 1 and roll.total == sum(faces) + 1 and roll.source == "void_assets"
    assert rules.choices(period, 2, 2)[1] == 1
    assert rules.choices(period, 2, 1)[1] == handler_count
    with pytest.raises(ValueError, match="instead of rerolling"):
        rules.roll(period, period.revision, 2, canon, (1, 1))
    assert canon.sheets["2"].heat == 300
    assert Period.model_validate_json(period.model_dump_json()) == period


def test_void_modifier_counts_both_families_including_damaged_assets(canon):
    canon.sheets["2"].assets[0].void = True
    canon.sheets["2"].assets[0].damaged = True
    canon.sheets["2"].assets.append(
        AssetState(id="frame-void", family="frame", name="Alteration", void=True)
    )
    assert rules.modifier(canon, 2) == 2
    period, _ = rolled(canon, (4, 4))
    assert period.progress["2"].roll.total == 10


@pytest.mark.parametrize("bad", [("hospital_stay", "medical_probing"), (), ("made_up",)])
def test_wrong_choice_counts_and_forged_options_are_rejected(canon, bad):
    period, _ = rolled(canon)
    with pytest.raises(ValueError, match="exact distinct"):
        rules.choose(period, period.revision, 2, 2, bad, "choice")
    with pytest.raises(ValueError, match="Only this Girl"):
        rules.choose(period, period.revision, 3, 2, ("hospital_stay",), "choice")


def test_hiding_options_are_conditional_and_choices_are_distinct_across_humans(canon):
    period, _ = rolled(canon, hiding=False)
    assert "become_dog" not in rules.choices(period, 2, 2)[0]
    with pytest.raises(ValueError):
        rules.choose(period, period.revision, 2, 2, ("become_dog",), "choice")
    period = rules.choose(period, period.revision, 2, 2, ("hospital_stay",), "actor")
    assert "hospital_stay" not in rules.choices(period, 2, 1)[0]
    with pytest.raises(ValueError):
        rules.choose(period, period.revision, 1, 2, ("hospital_stay",), "handler")
    period = rules.choose(period, period.revision, 1, 2, ("medical_probing",), "handler")
    assert rules.all_chosen(period, 2)
    with pytest.raises(ValueError, match="already saved"):
        rules.choose(period, period.revision, 2, 2, ("public_display_tag",), "again")


@pytest.mark.parametrize(
    "kind,owner",
    [
        ("medical_probing", 1),
        ("hospital_stay", 1),
        ("become_dog", 2),
        ("harpy_candidate_tag", 2),
        ("public_display_tag", 1),
        ("reprogram", 2),
    ],
)
def test_actual_outcomes_require_correct_human_details_and_apply_once(canon, kind, owner):
    period, canon = rolled(canon, (1, 1))
    period = rules.choose(period, period.revision, 2, 2, (kind,), "selection")
    selected = period.progress["2"].observation.outcomes[0]
    details = Details(account="Actual source consequence")
    if kind == "public_display_tag":
        details.tag = "Watched"
    if kind == "reprogram":
        details.identity = canon.sheets["2"].identities[0].id
    wrong = 1 if owner == 2 else 2
    with pytest.raises(ValueError, match="actual consequence decision owner"):
        rules.apply(
            period,
            period.revision,
            canon,
            wrong,
            2,
            selected.id,
            details,
            "apply",
            allow_duplicate_labels=True,
        )
    result, updated = rules.apply(
        period,
        period.revision,
        canon,
        owner,
        2,
        selected.id,
        details,
        "apply",
        allow_duplicate_labels=True,
    )
    assert selected.resolved is False and result.progress["2"].observation.outcomes[0].resolved
    assert updated.sheets["2"].heat == canon.sheets["2"].heat
    if kind in ("harpy_candidate_tag", "public_display_tag"):
        assert updated.sheets["2"].tags[-1].giver == 1
    with pytest.raises(ValueError, match="unapplied"):
        rules.apply(
            result,
            result.revision,
            updated,
            owner,
            2,
            selected.id,
            details,
            "again",
            allow_duplicate_labels=True,
        )


@pytest.mark.parametrize("family", ["girl", "frame"])
def test_surgical_removal_requires_current_void_asset_of_exact_family(canon, family):
    asset = next(x for x in canon.sheets["2"].assets if x.family == family)
    asset.void = True
    period, canon = rolled(canon, (1, 1))
    kind = "remove_" + family + "_void_asset"
    period = rules.choose(period, period.revision, 2, 2, (kind,), "selection")
    selected = period.progress["2"].observation.outcomes[0]
    with pytest.raises(ValueError, match="actual current Void Asset"):
        rules.apply(
            period,
            period.revision,
            canon,
            2,
            2,
            selected.id,
            Details(account="Surgery", asset="forged"),
            "apply",
            allow_duplicate_labels=True,
        )
    period, canon = rules.apply(
        period,
        period.revision,
        canon,
        2,
        2,
        selected.id,
        Details(account="Surgery", asset=asset.id),
        "apply",
        allow_duplicate_labels=True,
    )
    assert asset.id not in {x.id for x in canon.sheets["2"].assets}


def test_actual_selected_or_harsh_scene_and_all_effects_are_required_before_recovery(canon):
    period, canon = rolled(canon, (1, 1))
    period = rules.choose(period, period.revision, 2, 2, ("harpy_candidate_tag",), "choice")
    selected = period.progress["2"].observation.outcomes[0]
    with pytest.raises(ValueError):
        rules.scene(period, period.revision, 2, "observation:hospital_stay", (2, 1), "Not selected")
    period = rules.scene(
        period, period.revision, 2, "observation:harpy_candidate_tag", (2, 1), "Public review"
    )
    for actor in (2, 1):
        period = acknowledge_scene(period, period.revision, actor, 2)
    assert not rules.complete(period, 2)
    with pytest.raises(ValueError, match="Observation choices"):
        recovery(
            period, period.revision, 2, canon.sheets["2"], Recovery(), pending_effects=frozenset()
        )
    period, canon = rules.apply(
        period,
        period.revision,
        canon,
        2,
        2,
        selected.id,
        Details(account="Candidate designation"),
        "actual-effect",
        allow_duplicate_labels=True,
    )
    assert rules.complete(period, 2)
    result, _ = recovery(
        period, period.revision, 2, canon.sheets["2"], Recovery(), pending_effects=frozenset()
    )
    assert result.progress["2"].recovered


def test_harsh_scene_keeps_its_printed_girl_or_handler_requirement_with_extra_npc_controller(canon):
    period, _ = rolled(canon, (1, 1))
    period = rules.choose(period, period.revision, 2, 2, ("director_or_rival_arrives",), "choice")
    with pytest.raises(ValueError, match="another Girl or the Handler"):
        rules.scene(
            period,
            period.revision,
            2,
            "cell",
            (2, 4),
            "Only an NPC",
            extra_participants=frozenset({4}),
        )
