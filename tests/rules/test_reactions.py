import pytest
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_service import service

from girlframe.engine.m3_reactions import mark_obsolescence, princess_mission_end

ledger = ledger_fixture


@pytest.mark.parametrize("remaining", [0, 1, 2])
def test_sedation_approved_small_set_marks_all_available_without_synthetic_identities(
    ledger, remaining
):
    from girlframe.engine.m3_punishments import Details, apply

    _, game = service(ledger)
    before = state(game)
    before.sheets["2"].identities = before.sheets["2"].identities[:remaining]
    before.sheets["2"].heat = 8
    selected = tuple(x.id for x in before.sheets["2"].identities)
    result = apply(
        before,
        2,
        1,
        Details(kind="sedation", identities=selected),
        entity_id="synthetic",
        off_duty=False,
    )
    assert result.state.sheets["2"].heat == 0
    assert len(result.state.sheets["2"].identities) == remaining
    assert all(x.marked for x in result.state.sheets["2"].identities)
    assert before.sheets["2"].heat == 8


@pytest.mark.parametrize(
    "trigger", ["nanobot_injection", "mission_failure", "cadre_death", "high_budget"]
)
def test_obsolescence_printed_triggers_mark_one_and_scrapping_cannot_be_ignored(ledger, trigger):
    _, game = service(ledger, frame="DOCTORDOCTOR MK. II")
    before = state(game).sheets["2"]
    result = mark_obsolescence(before, trigger)
    assert result.sheet.obsolescence_marked == 1 and not result.replacement_required
    assert before.obsolescence_marked == 0
    before.obsolescence_marked = 7
    result = mark_obsolescence(before, trigger)
    assert result.sheet.obsolescence_marked == 8 and result.replacement_required
    assert result.sheet.frame_scrapped and not before.frame_scrapped
    with pytest.raises(ValueError):
        mark_obsolescence(result.sheet, trigger)


@pytest.mark.parametrize("policy,bonus", [("before_promotion", 0), ("after_promotion", 1)])
def test_princess_permission_timing_is_explicit_and_does_not_grant_normal_mission_rewards(
    ledger, policy, bonus
):
    _, game = service(ledger, girl="PRINCESS")
    before = state(game)
    before.order = (3, 2)
    updated = princess_mission_end(before, 2, upheld=True, ace_check=policy)
    assert updated.order == (2, 3)
    assert updated.sheets["2"].permissions == bonus
    assert before.order == (3, 2) and before.sheets["2"].permissions == 0
    already_ace = princess_mission_end(updated, 2, upheld=True, ace_check=policy)
    assert already_ace.sheets["2"].permissions == bonus + 1


def test_princess_condition_is_not_invented_and_missing_ruling_does_not_promote(ledger):
    _, game = service(ledger, girl="PRINCESS")
    before = state(game)
    assert princess_mission_end(before, 2, upheld=False, ace_check=None) == before
    with pytest.raises(ValueError, match="UNRESOLVED_RULING"):
        princess_mission_end(before, 2, upheld=True, ace_check=None)
