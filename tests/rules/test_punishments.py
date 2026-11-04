import pytest
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_service import service

from girlframe.engine.m2 import TagState, pair_key
from girlframe.engine.m3_core import Recovery, recover_off_duty
from girlframe.engine.m3_punishments import Details, apply

ledger = ledger_fixture


@pytest.fixture
def canon(ledger):
    _, game = service(ledger)
    return state(game)


def inflict(canon, details, **kwargs):
    return apply(canon, 2, 1, details, entity_id="synthetic-effect", off_duty=False, **kwargs)


def test_sedation_selects_exact_identities_without_generic_heat_and_locks_off_duty(canon):
    canon.sheets["2"].heat = 9
    choice = Details(kind="sedation", identities=("identity:0", "identity:1"))
    result = apply(canon, 2, 1, choice, entity_id="effect", off_duty=True)
    sheet = result.state.sheets["2"]
    assert sheet.heat == 0 and sum(x.marked for x in sheet.identities) == 2
    assert canon.sheets["2"].heat == 9 and not canon.sheets["2"].identities[0].marked
    with pytest.raises(ValueError, match="Sedation"):
        inflict(canon, Details(kind="sedation", identities=("identity:0", "identity:0")))
    with pytest.raises(ValueError, match="Sedation"):
        recover_off_duty(sheet, Recovery(unmark_identity="identity:0"))


def test_sedation_keeps_paired_owner_heat_and_last_identity_ankou_followups(canon):
    sheet = canon.sheets["2"]
    sheet.identities[0].paired = True
    sheet.frame = "PROJECT ANKOU"
    sheet.identities[2].marked = sheet.identities[3].marked = True
    result = inflict(canon, Details(kind="sedation", identities=("identity:0", "identity:1")))
    assert {x.kind for x in result.followups} == {"paired_identity_heat", "ankou_feedback"}
    assert result.state.sheets["2"].heat == 0


def test_beating_both_tags_and_damages_owned_girl_asset_with_last_asset_work(canon):
    canon.sheets["2"].assets[1].damaged = True
    result = inflict(canon, Details(kind="beating", asset="girl:0", tag="Bruised"))
    assert result.state.sheets["2"].tags[-1].giver == 1
    assert result.state.sheets["2"].assets[0].damaged
    assert result.followups[0].kind == "helpless"
    for asset in ("frame:0", "unowned", "girl:1"):
        with pytest.raises(ValueError):
            inflict(canon, Details(kind="beating", asset=asset, tag="Bruised"))


def test_reduced_socialization_erases_personal_and_quality_time_overflow_heats_both(canon):
    key = pair_key(2, 3)
    canon.bonds[key] = 1
    result = inflict(canon, Details(kind="reduced_socialization", bond_with=3))
    assert key not in result.state.bonds and canon.bonds[key] == 1
    canon.bonds[key] = 2
    result = apply(
        canon, 2, 3, Details(kind="quality_time", tag="Seen"), entity_id="effect", off_duty=False
    )
    assert result.state.sheets["2"].heat == result.state.sheets["3"].heat == 2
    assert result.state.bonds[key] == 2
    canon.bonds[pair_key(2, 1)] = 2
    result = inflict(canon, Details(kind="quality_time", tag="Heard"))
    assert result.state.sheets["2"].heat == result.state.handler_heat == 2


def test_demotion_and_stimulant_are_printed_effects_without_erasing_heat(canon):
    assert inflict(canon, Details(kind="demotion")).state.order == (3, 2)
    canon.sheets["2"].heat = 4
    assert inflict(canon, Details(kind="stimulant_injection")).state.sheets["2"].heat == 11


def test_moderate_consultation_protected_identity_and_force_embrace(canon):
    details = Details(kind="correctional_programming", identities=("identity:0",))
    with pytest.raises(ValueError, match="CONSULT_REQUIRED"):
        apply(canon, 2, 3, details, entity_id="effect", off_duty=False)
    assert len(inflict(canon, details).state.sheets["2"].identities) == 3
    canon.sheets["2"].identities[0].protected = True
    with pytest.raises(ValueError, match="protected"):
        inflict(canon, details)
    canon.sheets["2"].identities[0].protected = False
    canon.sheets["2"].tags.append(TagState(id="tag", label="Dutiful", giver=1))
    result = inflict(
        canon,
        Details(kind="correctional_programming", identities=("identity:1",), embrace_tag="tag"),
    )
    assert len(result.state.sheets["2"].identities) == 4
    assert result.state.sheets["2"].identities[-1].name == "Dutiful"
    assert result.state.sheets["2"].tags == []


def test_disassembly_surgery_and_inhibitor_are_canonical_and_immutable_inputs(canon):
    result = inflict(canon, Details(kind="frame_disassembly", asset="frame:0"))
    assert len(result.state.sheets["2"].assets) == len(canon.sheets["2"].assets) - 1
    result = inflict(
        canon,
        Details(
            kind="compliance_surgery",
            asset="girl:0",
            replacement_name="Synthetic prosthesis",
            replacement_description="Synthetic replacement",
        ),
    )
    assert len(result.state.sheets["2"].assets) == len(canon.sheets["2"].assets)
    assert result.state.sheets["2"].assets[-1].name == "Synthetic prosthesis"
    assert inflict(canon, Details(kind="libido_inhibitor")).state.sheets["2"].libido_inhibited
    assert not canon.sheets["2"].libido_inhibited


@pytest.mark.parametrize(
    "kind",
    [
        "revoked_privileges",
        "strict_regulations",
        "execution",
        "lobotomization",
        "indefinite_imprisonment",
        "link_surgery_reversal",
    ],
)
def test_unfinished_punishments_fail_closed(canon, kind):
    with pytest.raises(ValueError, match="UNSUPPORTED_RULE"):
        inflict(canon, Details(kind=kind))


def test_unrelated_fields_cannot_smuggle_extra_effects(canon):
    with pytest.raises(ValueError, match="unrelated"):
        inflict(canon, Details(kind="stimulant_injection", tag="Smuggled"))
