import pytest
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_reaction_service import mark, setup, work

from girlframe.engine.fanbase import Fanbase
from girlframe.engine.m3_frame_state import Package, Preferences, SuppliedAsset
from girlframe.engine.m3_replacement import different_frame, replace

ledger = ledger_fixture


@pytest.fixture
def inputs(ledger):
    svc, missions, game, mission = setup(ledger, boxes=7)
    mark(svc, work(missions, mission, "doctor_obsolescence")["id"])
    return state(game), missions.access.registry


def supplied(count=2, **kwargs):
    return Package(
        assets=tuple(
            SuppliedAsset(
                name="Synthetic " + str(i),
                description="Handler-specified package",
                damaged=False,
                void=False,
            )
            for i in range(count)
        ),
        explanation="Explicit Handler-defined replacement",
        **kwargs,
    )


def apply(before, registry, frame="THE ENFORCER", package=None, **kwargs):
    return replace(
        before,
        2,
        Preferences(frame=frame, **kwargs),
        package or supplied(),
        registry,
        work_id="synthetic-work",
        frame_id="synthetic-frame",
        court_accepted=True,
    )


@pytest.mark.parametrize("count", [0, 1, 2, 5])
def test_free_replacement_uses_exact_handler_asset_count_and_preserves_girl_resources(
    inputs, count
):
    before, registry = inputs
    before.sheets["2"].heat = 9
    before.sheets["2"].permissions = 3
    before.sheets["2"].identities[0].marked = True
    result = apply(before, registry, package=supplied(count))
    old, new = before.sheets["2"], result.sheets["2"]
    assert len([x for x in new.assets if x.family == "frame"]) == count
    assert [x for x in new.assets if x.family == "girl"] == [
        x for x in old.assets if x.family == "girl"
    ]
    assert new.heat == 9 and new.permissions == 3 and new.identities == old.identities
    assert result.bonds == before.bonds and result.order == before.order
    assert new.frame == "THE ENFORCER" and not new.frame_scrapped and new.obsolescence_marked == 0
    assert new.frame_runtime.generation == 1
    assert old.frame_scrapped and old.frame == "DOCTORDOCTOR MK. II"


@pytest.mark.parametrize(
    "current,chosen", [("JANUS", "JANUS-B"), ("JANUS-B", "JANUS"), ("THE ENFORCER", "the enforcer")]
)
def test_official_aliases_cannot_bypass_different_playbook(current, chosen):
    with pytest.raises(ValueError, match="different"):
        different_frame(current, chosen)


def test_wyvern_intrinsic_and_consume_handler_track_are_not_hidden_defaults(inputs):
    before, registry = inputs
    result = apply(before, registry, frame="WYVERN 0.4", package=supplied(4))
    assert len([x for x in result.sheets["2"].assets if x.family == "frame"]) == 5
    assert result.sheets["2"].assets[-1].name == "Enormous"
    full = apply(before, registry, frame="WYVERN 0.4", package=supplied(5))
    assert len([x for x in full.sheets["2"].assets if x.family == "frame"]) == 6
    assert full.sheets["2"].assets[-1].intrinsic == "wyvern_enormous"
    with pytest.raises(ValueError):
        supplied(6)
    with pytest.raises(ValueError, match="hunger"):
        apply(before, registry, frame="CONSUME")
    result = apply(before, registry, frame="CONSUME", package=supplied(1, consume_hunger="Gnawing"))
    assert result.sheets["2"].frame_runtime.consume_hunger == "Gnawing"


def test_new_janus_core_is_distinct_unnamed_and_prince_requires_owner_fanbase(inputs):
    before, registry = inputs
    result = apply(before, registry, frame="JANUS")
    assert result.sheets["2"].frame == "JANUS-B"
    runtime = result.sheets["2"].frame_runtime
    assert runtime.core_id != runtime.id and runtime.harpy_core.tags[0] == "Drugged"
    with pytest.raises(ValueError, match="fanbase"):
        apply(before, registry, frame="THE PRINCE")
    fanbase = Fanbase(
        demographics=("Young boys", "Online shippers"),
        demanded=("Sexy", "A leader"),
        rejected=("Girly", "Kind"),
    )
    result = apply(before, registry, frame="THE PRINCE", fanbase=fanbase)
    assert len(result.sheets["2"].identities) == len(before.sheets["2"].identities) + 2
    assert all(x.protected for x in result.sheets["2"].identities[-2:])


def test_new_court_requires_real_recipient_response_and_supported_extra_rules_only(inputs):
    before, registry = inputs
    preference = Preferences(frame="THE RED QUEEN", court_role="The Knight", court_target=3)
    with pytest.raises(ValueError, match="explicitly accept"):
        replace(
            before,
            2,
            preference,
            supplied(),
            registry,
            work_id="work",
            frame_id="frame",
            court_accepted=False,
        )
    result = replace(
        before,
        2,
        preference,
        supplied(),
        registry,
        work_id="work",
        frame_id="frame",
        court_accepted=True,
    )
    assert result.sheets["2"].frame_runtime.court["The Knight"] == 3
    assert sum(x == 2 for x in result.sheets["2"].frame_runtime.court.values()) == 4
    handler_choice = Preferences(frame="THE RED QUEEN", court_role="The Knight", court_target=1)
    result = replace(
        before,
        2,
        handler_choice,
        supplied(),
        registry,
        work_id="work",
        frame_id="handler-frame",
        court_accepted=True,
    )
    assert result.handler_tags[-1].label == "The Knight" and result.handler_tags[-1].giver == 2
    with pytest.raises(ValueError, match="UNSUPPORTED_RULE"):
        apply(before, registry, package=supplied(additional_rules=("not-a-rule",)))


def test_changeling_strings_reference_actual_bonds_not_arbitrary_characters(inputs):
    before, registry = inputs
    result = apply(before, registry, frame="CHANGELING", package=supplied(psych_strings=(3,)))
    assert result.sheets["2"].frame_runtime.psych_strings == (3,)
    with pytest.raises(ValueError, match="Bonds"):
        apply(before, registry, frame="CHANGELING", package=supplied(psych_strings=(999,)))
