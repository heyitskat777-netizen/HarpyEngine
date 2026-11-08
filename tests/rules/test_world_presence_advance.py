"""An actual absent body has no map action; other bodies still finish their actual period."""

from uuid import uuid4

import pytest
from test_actors import canon as canon
from test_actors import ledger as ledger
from test_ledger import ADMIN
from test_m2_game import state
from test_off_duty_cycle import activate, call, finish_routine, prepared, recover_both
from test_world import gorgon

from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_harpy_defeat_state import Travel
from girlframe.engine.m3_world import Movement, update
from girlframe.engine.m3_world_advance import advance, plan, steps
from girlframe.engine.m3_world_state import Goal
from girlframe.services.m3_world import WorldService


def absent(state, actor):
    body = resolve(state, actor, ())
    state.harpy_travels.append(
        Travel(
            id="reviewed-" + actor.token,
            actor=actor,
            controller=body.controller,
            source_event="actual-owned-route",
            source_sha256=body.source_sha256,
            rift="actual-rift",
            travels_frame=False,
            destination=None,
            account="Actual source crossing",
            navigation="Actual source navigation",
            judge=1,
            appointment="actual-appointment",
            state="offstage",
            response_event="actual-route-review",
        )
    )
    return state


def test_offstage_aggressive_does_not_destroy_cached_base_while_present_one_destroys_real_city(
    canon,
):
    old = gorgon("aggressive", "absent", cell=(0, 0))
    present = gorgon("aggressive", "present", cell=(0, 4))
    canon.world = update(canon.world, gorgons=(old, present))
    absent(canon, ActorRef(kind="gorgon", entity=old.id))
    before = canon.model_dump_json()
    result, deferred = advance(canon, "actual-world-period", (), ())
    assert next(x for x in result.world.locations if x.id == "base0").condition == "intact"
    assert next(x for x in result.world.locations if x.id == "city0").condition == "destroyed"
    assert result.world.gorgons[0] == old
    assert [x.kind for x in result.followups] == ["budget_structure_destroyed"]
    assert deferred[0]["actor"] == ActorRef(kind="gorgon", entity=old.id).model_dump_json()
    assert canon.model_dump_json() == before
    with pytest.raises(ValueError, match="once"):
        advance(canon.model_copy(update={"world": result.world}), "actual-world-period", (), ())


def test_actual_offstage_npc_goal_does_not_authorize_cached_directed_step(canon):
    target = ActorRef(kind="npc", entity="2")
    hunter = gorgon("directed", "pursuer", cell=(2, 2), goal=Goal(kind="npc", entity_id="2"))
    other = gorgon("directed", "other", cell=(3, 3), goal=Goal(kind="location", entity_id="base0"))
    canon.world = update(canon.world, gorgons=(hunter, other))
    absent(canon, target)
    assert plan(canon)[0] == frozenset({"other"})
    assert "pursuer" not in steps(canon)
    with pytest.raises(ValueError, match="every Directed"):
        advance(canon, "cannot-use-cache", (Movement(gorgon="pursuer", destination=(1, 1)),), ())
    result, deferred = advance(
        canon,
        "real-world-period",
        (Movement(gorgon="other", destination=steps(canon)["other"][0]),),
        (),
    )
    assert result.world.gorgons[0] == hunter and result.world.gorgons[1].cell != other.cell
    assert deferred and result.world.completed_off_duty == ("real-world-period",)


def test_genuine_owned_period_completes_without_forcing_absent_directed_body_to_return(ledger):
    cycle, game, identity = prepared(ledger)
    activate(cycle, game, identity)
    recover_both(cycle, game, identity)
    with ledger.transaction() as c:
        canon = state(game)
        hunter = next(x for x in canon.world.gorgons if x.gorgon_class == "directed")
        absent(canon, ActorRef(kind="gorgon", entity=hunter.id))
        game.event(c, 1, str(uuid4()), "synthetic.actual_reviewed_world_travel", canon)
    finish_routine(cycle, game, identity)
    before = state(game)
    preview = WorldService(cycle.missions).advancement(ADMIN)
    assert hunter.id not in preview["advancing_gorgons"]
    outcome = call(cycle, game, ADMIN, identity, "finish", ())
    after = state(game)
    assert outcome["phase"] == "complete"
    assert next(x for x in after.world.gorgons if x.id == hunter.id) == hunter
    assert (
        after.harpy_travels == before.harpy_travels and after.harpy_travels[-1].state == "offstage"
    )
    assert after.world.completed_off_duty == (identity,)
    assert any(
        x.get("kind") == "world_advancement_absent" and x.get("period") == identity
        for x in after.facts
    )
    assert cycle.periods.current(ADMIN) is None


def test_actual_killed_npc_goal_defers_only_its_directed_hunter_without_resurrecting_body(canon):
    from girlframe.engine.m3_gorgon import NpcAttack, attack_npc

    hunter = gorgon("directed", "pursuer", cell=(2, 2), goal=Goal(kind="npc", entity_id="2"))
    other = gorgon("directed", "other", cell=(3, 3), goal=Goal(kind="location", entity_id="base0"))
    killer = gorgon("aggressive", "actual-killer", cell=(0, 0))
    canon.world = update(canon.world, gorgons=(hunter, other, killer))
    actor, victim = ActorRef(kind="gorgon", entity=killer.id), ActorRef(kind="npc", entity="2")
    original_pc = canon.sheets["2"].model_dump_json()
    killed = attack_npc(
        canon,
        NpcAttack(
            attacker=actor,
            target=victim,
            assets=(killer.assets[0].id,),
            attacker_sha256=resolve(canon, actor, ()).source_sha256,
            target_sha256=resolve(canon, victim, ()).source_sha256,
            account="Actual source Gorgon attack kills its actual NPC victim",
            trigger_confirmed=True,
        ),
        "actual-npc-ending-event",
    )
    present, deferred = plan(killed)
    assert "pursuer" not in present and {"other", "actual-killer"} <= present
    proof = next(x for x in deferred if x["source"] == "actual_goal_ended")
    import json

    assert json.loads(proof["endpoint"])["id"] == "2"
    assert not json.loads(proof["endpoint"])["alive"]
    result, _ = advance(
        killed,
        "actual-period-after-goal-died",
        (Movement(gorgon="other", destination=steps(killed)["other"][0]),),
        (),
    )
    assert result.world.gorgons[0] == hunter
    assert result.world.gorgons[1].cell != other.cell
    assert not result.world.npcs[0].alive and result.world.npcs[0].cell == (0, 0)
    assert killed.sheets["2"].model_dump_json() == original_pc
    assert result.world.completed_off_duty == ("actual-period-after-goal-died",)
