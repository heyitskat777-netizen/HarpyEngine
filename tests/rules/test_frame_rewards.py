import pytest
from test_ledger import ledger as ledger_fixture
from test_m2_game import setup_game, state
from test_world import initial

from girlframe.engine.fanbase import Fanbase
from girlframe.engine.m3_frame_rewards import Claim, queen, queen_award, review
from girlframe.engine.m3_frame_state import FrameRuntime
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import AdversaryPilot, Asset, Faction, Npc
from girlframe.engine.shared_setup import AcceptedSetup

ledger = ledger_fixture


@pytest.fixture
def canon(ledger):
    game, *_ = setup_game(ledger)
    return state(game)


def context(canon, frame):
    canon.sheets["2"].frame = frame
    if frame == "THE PRINCE":
        canon.sheets["2"].frame_runtime = FrameRuntime(
            id="prince",
            generation=1,
            source_work="replacement",
            fanbase=Fanbase(
                demographics=("Young boys", "Young girls"),
                demanded=("Kind", "Intelligent"),
                rejected=("Dangerous", "Relatable"),
            ),
        )
    world = initial()
    npc = Npc(
        id="prisoner",
        name="Captured person",
        jobs=("prisoner",),
        detail="An actual role",
        cell=(0, 0),
        controller=1,
        faction="rebels",
        revealed=True,
        custody_event="actual-custody-source",
    )
    canon.world = update(
        world,
        factions=(Faction(id="rebels", name="Rebels", kind="rebel", cells=((0, 0),)),),
        npcs=(npc,),
    )
    return canon


@pytest.mark.parametrize(
    "frame,details",
    [
        ("THE PRINCE", {}),
        ("CONSUME", {"prisoner": "npc:prisoner"}),
        ("JANUS-B", {"official": "handler:1"}),
        ("WYVERN 0.4", {"offering": "An unusual sample"}),
        ("THE ENFORCER", {"prisoner": "npc:prisoner"}),
        ("THE ENFORCER", {"evidence": "A factual report of a cadremate's refusal"}),
        ("CHANGELING", {"influenced_pilot": 3}),
        ("PROJECT ANKOU", {}),
    ],
)
def test_each_conditional_bonus_grants_one_permission_on_actual_owner_review(canon, frame, details):
    current = context(canon, frame)
    before = current.sheets["2"].permissions
    result = review(
        current,
        2,
        Claim(fulfilled=True, account="The actual source-specific trigger occurred", **details),
        "owned-review",
        handler_interested=True if frame == "WYVERN 0.4" else None,
    )
    assert result.sheets["2"].permissions == before + 1
    assert current.sheets["2"].permissions == before
    assert result.sheets["3"].permissions == current.sheets["3"].permissions
    with pytest.raises(ValueError, match="already saved"):
        review(
            result,
            2,
            Claim(fulfilled=True, account="No second grant", **details),
            "owned-review",
            handler_interested=True if frame == "WYVERN 0.4" else None,
        )


@pytest.mark.parametrize(
    "frame",
    (
        "THE PRINCE",
        "CONSUME",
        "JANUS-B",
        "WYVERN 0.4",
        "THE ENFORCER",
        "CHANGELING",
        "PROJECT ANKOU",
    ),
)
def test_no_trigger_is_an_explicit_owned_record_without_free_permissions(canon, frame):
    current = context(canon, frame)
    result = review(
        current, 2, Claim(fulfilled=False, account="This condition did not occur"), "review"
    )
    assert result.sheets["2"].permissions == current.sheets["2"].permissions
    with pytest.raises(ValueError, match="contradictory"):
        review(
            current,
            2,
            Claim(fulfilled=False, account="No trigger", offering="Unrelated"),
            "other-review",
        )


@pytest.mark.parametrize(
    "frame,details",
    [
        ("CONSUME", {}),
        ("JANUS-B", {"official": "handler:99"}),
        ("WYVERN 0.4", {}),
        ("CHANGELING", {"influenced_pilot": 2}),
        ("THE ENFORCER", {}),
        ("THE ENFORCER", {"prisoner": "npc:prisoner", "evidence": "Choose both"}),
    ],
)
def test_source_specific_missing_and_unrelated_choices_do_not_grant_rewards(canon, frame, details):
    current = context(canon, frame)
    with pytest.raises(ValueError):
        review(current, 2, Claim(fulfilled=True, account="Invalid claim", **details), "review")
    assert current.sheets["2"].permissions == 0


def test_prisoner_reward_cannot_invent_capture_transport_or_rebel_affiliation(canon):
    current = context(canon, "CONSUME")
    pilot = AdversaryPilot(
        id="harpy",
        name="A free Harpy",
        kind="harpy",
        girl="MOCKINGBIRD",
        frame="JANUS-B",
        assets=(Asset(id="a", name="Armour", description="An actual capability", family="frame"),),
        controller=3,
        cell=(0, 0),
    )
    current.world = update(current.world, pilots=(pilot,))
    choice = Claim(fulfilled=True, account="A purported delivery", prisoner="pilot:harpy")
    with pytest.raises(ValueError, match="actual custody"):
        review(current, 2, choice, "review")
    captured = pilot.model_copy(
        update={"custody": "captured", "custodian": 2, "custody_event": "actual-source"}
    )
    current.world = update(current.world, pilots=(captured,))
    assert review(current, 2, choice, "review").sheets["2"].permissions == 1
    current.sheets["2"].frame = "THE ENFORCER"
    with pytest.raises(ValueError, match="Rebel prisoner"):
        review(current, 2, choice, "review")
    current.world = update(current.world, pilots=(captured.model_copy(update={"cell": (1, 1)}),))
    current.sheets["2"].frame = "CONSUME"
    with pytest.raises(ValueError, match="delivery"):
        review(current, 2, choice, "review")


def test_queen_holder_is_resolved_from_actual_initial_or_runtime_court_and_owns_choice(canon):
    sheet = canon.sheets["2"]
    sheet.frame = "THE RED QUEEN"
    sheet.review = sheet.review.model_copy(
        update={
            "shared": (
                AcceptedSetup(
                    id="court",
                    revision=1,
                    kind="court",
                    source_id=2,
                    target_id=3,
                    value="The Queen",
                ),
            )
        }
    )
    assert queen(sheet) == 3
    with pytest.raises(ValueError, match="actual Queen"):
        queen_award(canon, 2, 1, 2, "queen-choice")
    with pytest.raises(ValueError, match="itself while it is the Dog"):
        queen_award(canon, 2, 3, 3, "queen-choice")
    result = queen_award(canon, 2, 3, 2, "queen-choice")
    assert result.sheets["2"].permissions == 1
    with pytest.raises(ValueError, match="again"):
        queen_award(result, 2, 3, 2, "queen-choice")
    sheet.frame_runtime = FrameRuntime(
        id="new", generation=1, source_work="actual-replacement", court={"The Queen": 2}
    )
    assert queen(sheet) == 2
    # The self-award restriction applies to the holder: another Girl may be the Dog.
    assert queen_award(canon, 2, 2, 3, "new-queen-choice").sheets["3"].permissions == 1


def test_one_delivery_is_not_reused_but_joint_contributors_have_no_invented_quota(canon):
    current = context(canon, "CONSUME")
    choice = Claim(
        fulfilled=True, account="I took part in the actual delivery", prisoner="npc:prisoner"
    )
    first = review(current, 2, choice, "first", character_id="character-two")
    with pytest.raises(ValueError, match="already earned"):
        review(first, 2, choice, "later-period", character_id="character-two")
    first.sheets["3"].frame = "CONSUME"
    joint = review(first, 3, choice, "joint", character_id="character-three")
    assert joint.sheets["2"].permissions == joint.sheets["3"].permissions == 1
    assert len([x for x in joint.facts if x.get("custody_source") == "actual-custody-source"]) == 2


def test_historical_frame_evaluation_grants_only_current_permission_without_state_reset(canon):
    prior = context(canon, "JANUS-B")
    current = type(prior).model_validate_json(prior.model_dump_json())
    current.sheets["2"].frame = "CONSUME"
    current.sheets["2"].heat = 20
    current.sheets["2"].permissions = 4
    current.world = update(current.world, territory=frozenset({(1, 1)}))
    result = review(
        current,
        2,
        Claim(
            fulfilled=True, official="handler:1", account="The prior Frame's demonstrated condition"
        ),
        "review",
        eligibility=prior,
    )
    assert result.sheets["2"].frame == "CONSUME" and result.sheets["2"].heat == 20
    assert result.sheets["2"].permissions == 5 and result.world == current.world
