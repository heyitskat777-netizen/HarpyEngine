"""Printed NPC death uses the actual NPC, not its human controller's Girl sheet."""

import pytest
from pydantic import ValidationError
from test_actors import bindings
from test_actors import canon as canon
from test_actors import ledger as ledger
from test_world import gorgon

from girlframe.engine import m3_gorgon as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Goal


def prepared(canon):
    canon.world = update(canon.world, gorgons=(*canon.world.gorgons, gorgon("erratic", "attacker")))
    first = resolve(canon, ActorRef(kind="gorgon", entity="attacker"), bindings(canon))
    target = resolve(canon, ActorRef(kind="npc", entity="2"), bindings(canon))
    return rules.NpcAttack(
        attacker=first.ref,
        target=target.ref,
        assets=(first.assets[0].id,),
        attacker_sha256=first.source_sha256,
        target_sha256=target.source_sha256,
        account="PRIVATE_ACTUAL_ATTACK_AND_REACH",
        trigger_confirmed=True,
    )


def test_printed_npc_death_preserves_same_human_girl_every_resource_and_other_world_actors(canon):
    attack = prepared(canon)
    before = canon.model_dump_json()
    result = rules.attack_npc(canon, attack, "actual-attack-event")
    assert canon.model_dump_json() == before
    assert not result.world.npcs[0].alive
    assert result.sheets == canon.sheets and result.order == canon.order
    assert result.handler_heat == canon.handler_heat and result.bonds == canon.bonds
    assert result.world.gorgons == canon.world.gorgons
    assert result.world.pilots == canon.world.pilots
    assert result.world.npcs[1:] == canon.world.npcs[1:]
    assert result.world.npcs[0].model_dump(exclude={"alive"}) == canon.world.npcs[0].model_dump(
        exclude={"alive"}
    )
    fact = result.facts[-1]
    assert fact["source_event"] == "actual-attack-event"
    assert rules.NpcAttack.model_validate_json(fact["attack"]) == attack
    with pytest.raises(ValueError, match="living actual NPC"):
        rules.attack_npc(result, attack, "repeat-death")


@pytest.mark.parametrize("role", ("attacker", "target"))
def test_actual_actor_fingerprints_reject_stale_attack_without_modifying_input(canon, role):
    attack = prepared(canon).model_copy(update={role + "_sha256": "0" * 64})
    before = canon.model_dump_json()
    with pytest.raises(ValueError, match="STALE_ATTACK"):
        rules.attack_npc(canon, attack, "source")
    assert canon.model_dump_json() == before


@pytest.mark.parametrize("assets", (("foreign",), ("attacker:0", "attacker:0"), ()))
def test_unknown_duplicated_or_empty_assets_cannot_attack(canon, assets):
    attack = prepared(canon).model_copy(update={"assets": assets})
    with pytest.raises((ValueError, ValidationError)):
        rules.attack_npc(canon, attack, "source")


def test_actual_damaged_asset_cannot_be_used_even_with_fresh_fingerprint(canon):
    attack = prepared(canon)
    g = canon.world.gorgons[-1]
    g = g.model_copy(
        update={"assets": (g.assets[0].model_copy(update={"damaged": True}), *g.assets[1:])}
    )
    canon.world = update(canon.world, gorgons=(*canon.world.gorgons[:-1], g))
    first = resolve(canon, attack.attacker, ())
    attack = attack.model_copy(update={"attacker_sha256": first.source_sha256})
    with pytest.raises(ValueError, match="undamaged Assets"):
        rules.attack_npc(canon, attack, "source")


@pytest.mark.parametrize("kind", ("benevolent", "dormant"))
def test_benevolent_prohibition_and_unported_awakening_are_not_bypassed(canon, kind):
    prepared(canon)
    canon.world = update(canon.world, gorgons=(gorgon(kind, "attacker"),))
    with pytest.raises(ValueError, match="Benevolent|awakening"):
        rules.eligible(
            canon, ActorRef(kind="gorgon", entity="attacker"), ActorRef(kind="npc", entity="2")
        )


def test_director_does_not_silently_waive_its_required_death_work(canon):
    attack = prepared(canon)
    target = canon.world.npcs[0].model_copy(update={"jobs": ("director",)})
    canon.world = update(canon.world, npcs=(target, *canon.world.npcs[1:]))
    with pytest.raises(ValueError, match="replacement resolver"):
        rules.eligible(canon, attack.attacker, attack.target)


def test_another_handler_is_an_npc_and_does_not_borrow_the_campaign_handler_rules(canon):
    attack = prepared(canon)
    target = resolve(canon, ActorRef(kind="npc", entity="npc-handler"), ())
    attack = attack.model_copy(update={"target": target.ref, "target_sha256": target.source_sha256})
    result = rules.attack_npc(canon, attack, "actual-npc-handler-death")
    assert not result.world.npcs[-1].alive
    assert result.handler == canon.handler and result.handler_heat == canon.handler_heat
    assert result.sheets == canon.sheets and result.director_contexts == canon.director_contexts


def test_directed_goal_death_defers_only_actual_hunter_through_existing_world_port(canon):
    attack = prepared(canon)
    directed = gorgon("directed", "goal-seeker", goal=Goal(kind="npc", entity_id="2"))
    canon.world = update(canon.world, gorgons=(*canon.world.gorgons, directed))
    from girlframe.engine.m3_world_advance import plan

    result = rules.attack_npc(canon, attack, "actual-directed-goal-ending")
    present, deferred = plan(result)
    assert "goal-seeker" not in present
    assert next(x for x in deferred if x["source"] == "actual_goal_ended")
    assert result.world.npcs[0].cell == canon.world.npcs[0].cell
    assert not result.world.npcs[0].alive and result.sheets == canon.sheets


def test_no_invented_ranged_reach_movement_or_forged_player_target(canon):
    attack = prepared(canon)
    target = canon.world.npcs[0].model_copy(update={"cell": (1, 1)})
    canon.world = update(canon.world, npcs=(target, *canon.world.npcs[1:]))
    with pytest.raises(ValueError, match="co-located"):
        rules.eligible(canon, attack.attacker, attack.target)
    with pytest.raises(ValueError, match="ordinary NPC"):
        rules.eligible(canon, attack.attacker, ActorRef(kind="pilot", entity="2", incarnation="pc"))


def test_attack_needs_new_nonblank_actual_source(canon):
    attack = prepared(canon)
    with pytest.raises(ValueError, match="new source"):
        rules.attack_npc(canon, attack, " ")
    canon.facts.append({"kind": "prior-source", "source_event": "already-used"})
    with pytest.raises(ValueError, match="new source"):
        rules.attack_npc(canon, attack, "already-used")
