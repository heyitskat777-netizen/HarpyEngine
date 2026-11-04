"""Asset destruction is distinct from damage, exposed Core and actual death."""

import pytest
from pydantic import ValidationError
from test_actors import canon as canon
from test_actors import ledger as ledger
from test_world import gorgon

from girlframe.engine import m3_gorgon_combat as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_world import update, validate_initial_gorgon


def setup(canon, *, defender="erratic"):
    canon.world = update(
        canon.world,
        gorgons=(gorgon("erratic", "attacker"), gorgon(defender, "defender")),
    )
    return canon


def choice(canon, *, winner="attacker", **overrides):
    first, second = (
        resolve(canon, ActorRef(kind="gorgon", entity=identity), ())
        for identity in ("attacker", "defender")
    )
    values = dict(
        attacker=first.ref,
        defender=second.ref,
        attacking_assets=(first.assets[0].id,),
        defending_assets=(second.assets[0].id,),
        attacker_sha256=first.source_sha256,
        defender_sha256=second.source_sha256,
        winner=winner,
        losing_asset=second.assets[0].id if winner == "attacker" else first.assets[0].id,
        approach="direct",
        account="PRIVATE_ACTUAL_CONTEST_AND_HANDLER_WINNER",
        trigger_confirmed=True,
    )
    return rules.Contest(**(values | overrides))


@pytest.mark.parametrize("winner", ("attacker", "defender"))
def test_actual_handler_winner_destroys_one_owned_pitted_asset_and_preserves_every_other_actor(
    canon, winner
):
    setup(canon)
    original = canon.model_dump_json()
    pick = choice(canon, winner=winner)
    result = rules.contest(canon, pick, "actual-source")
    assert canon.model_dump_json() == original
    loser = result.world.gorgons[1 if winner == "attacker" else 0]
    assert len(loser.assets) == 3 and len(loser.destroyed_assets) == 1
    assert loser.destroyed_assets[0].id == pick.losing_asset
    assert not loser.destroyed_assets[0].damaged
    assert loser.alive and not loser.exposed
    assert result.sheets == canon.sheets and result.world.npcs == canon.world.npcs
    assert result.bonds == canon.bonds and result.order == canon.order
    assert rules.Contest.model_validate_json(result.facts[-1]["contest"]) == pick
    view = resolve(result, ActorRef(kind="gorgon", entity=loser.id), ())
    assert pick.losing_asset not in {x.id for x in view.assets}


def test_last_asset_destruction_keeps_gorgon_alive_and_retains_actual_core_plan(canon):
    setup(canon)
    original_plan = canon.world.gorgons[1].core_plan
    for index in range(4):
        canon = rules.contest(canon, choice(canon), "actual-contest-" + str(index))
    defeated = canon.world.gorgons[1]
    assert not defeated.assets and len(defeated.destroyed_assets) == 4
    assert defeated.alive and not defeated.exposed and defeated.core_plan == original_plan
    with pytest.raises(ValueError, match="undamaged Asset"):
        rules.eligible(
            canon,
            ActorRef(kind="gorgon", entity="attacker"),
            ActorRef(kind="gorgon", entity="defender"),
        )
    with pytest.raises(ValueError, match="destroyed Asset history"):
        validate_initial_gorgon(defeated)


@pytest.mark.parametrize("who", ("attacker", "defender"))
def test_stale_original_actor_cannot_destroy_any_asset(canon, who):
    setup(canon)
    pick = choice(canon).model_copy(update={who + "_sha256": "0" * 64})
    before = canon.model_dump_json()
    with pytest.raises(ValueError, match="STALE_CONTEST"):
        rules.contest(canon, pick, "actual-source")
    assert canon.model_dump_json() == before


@pytest.mark.parametrize(
    "field,value",
    (
        ("attacking_assets", ("foreign",)),
        ("defending_assets", ("attacker:0",)),
        ("losing_asset", "defender:1"),
    ),
)
def test_unknown_cross_owned_or_unpitted_asset_cannot_be_destroyed(canon, field, value):
    setup(canon)
    pick = choice(canon).model_copy(update={field: value})
    with pytest.raises(ValueError, match="owned Assets|actually pitted"):
        rules.contest(canon, pick, "actual-source")
    assert all(not x.destroyed_assets for x in canon.world.gorgons)


def test_directed_protection_requires_an_actual_indirect_contest_account(canon):
    setup(canon, defender="directed")
    with pytest.raises(ValueError, match="protective"):
        rules.contest(canon, choice(canon), "direct-cannot")
    result = rules.contest(
        canon,
        choice(
            canon, approach="indirect", account="The actual indirect approach bypasses the shield"
        ),
        "indirect-source",
    )
    assert result.world.gorgons[1].destroyed_assets[0].id == "defender:0"
    assert result.world.gorgons[1].protected_asset == "defender:0"
    # Its destroyed guard no longer protects the other actual current Assets.
    result = rules.contest(result, choice(result), "later-direct-source")
    assert len(result.world.gorgons[1].destroyed_assets) == 2


def test_benevolent_can_defend_in_anothers_contest_but_cannot_initiate_attack(canon):
    setup(canon, defender="benevolent")
    result = rules.contest(canon, choice(canon, winner="defender"), "actual-defense")
    assert result.world.gorgons[0].destroyed_assets and result.world.gorgons[1].alive
    with pytest.raises(ValueError, match="Benevolent"):
        rules.eligible(
            canon,
            ActorRef(kind="gorgon", entity="defender"),
            ActorRef(kind="gorgon", entity="attacker"),
        )


def test_dormancy_ranged_and_non_gorgon_branches_still_require_actual_resolvers(canon):
    setup(canon, defender="dormant")
    first, second = (
        ActorRef(kind="gorgon", entity="attacker"),
        ActorRef(kind="gorgon", entity="defender"),
    )
    with pytest.raises(ValueError, match="awakening"):
        rules.eligible(canon, first, second)
    setup(canon)
    moved = canon.world.gorgons[1].model_copy(update={"cell": (1, 0)})
    canon.world = update(canon.world, gorgons=(canon.world.gorgons[0], moved))
    with pytest.raises(ValueError, match="co-located"):
        rules.eligible(canon, first, second)
    with pytest.raises(ValueError, match="two distinct"):
        rules.eligible(canon, first, first)
    with pytest.raises(ValueError, match="two distinct"):
        rules.eligible(canon, first, ActorRef(kind="external_pilot", entity="external"))


def test_core_requires_both_actual_asset_condition_and_separate_confirmed_weakness(canon):
    setup(canon)
    ref = ActorRef(kind="gorgon", entity="defender")

    def exposure(state):
        actor = resolve(state, ref, ())
        return rules.Exposure(
            actor=ref,
            source_sha256=actor.source_sha256,
            account="PRIVATE_ACTUAL_CORE_WEAKNESS",
            weakness_confirmed=True,
        )

    with pytest.raises(ValueError, match="designated"):
        rules.expose(canon, exposure(canon), "too-early")
    after = rules.contest(canon, choice(canon), "actual-guard-destruction")
    assert after.world.gorgons[1].alive and not after.world.gorgons[1].exposed
    with pytest.raises(ValidationError):
        rules.expose(
            after, exposure(after).model_copy(update={"weakness_confirmed": False}), "not-confirmed"
        )
    with pytest.raises(ValueError, match="STALE_CORE"):
        rules.expose(after, exposure(canon), "stale-core")
    result = rules.expose(after, exposure(after), "actual-core-exposure")
    assert result.world.gorgons[1].exposed and result.world.gorgons[1].alive
    assert after.world.gorgons[1].exposed is False
    with pytest.raises(ValueError, match="actual living"):
        rules.expose(result, exposure(result), "repeated-exposure")


def test_model_retains_only_distinct_actual_current_and_destroyed_owned_assets(canon):
    setup(canon)
    target = canon.world.gorgons[1]
    with pytest.raises(ValidationError, match="distinct"):
        update(
            canon.world,
            gorgons=(target.model_copy(update={"destroyed_assets": (target.assets[0],)}),),
        )
    with pytest.raises(ValidationError, match="original Gorgon"):
        update(canon.world, gorgons=(target.model_copy(update={"assets": target.assets[1:]}),))
