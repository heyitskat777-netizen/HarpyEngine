"""Actual owned battle declarations, independent source facts and pre-dice stale checks."""

from uuid import uuid4

import pytest
from test_beneath_service import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_physical_operations import place
from test_world import initial

from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_battle_state import Declaration
from girlframe.services.m3_battle import BattleService, pre_roll, prepare
from girlframe.services.onboarding import WorkflowError


def prepared(store, *, girl=None):
    if girl is None:
        game, worker, gateway = ready(store)
    else:
        from test_m2_game import Gateway
        from test_mission_service import service

        from girlframe.delivery.m2_worker import GameWorker

        _, game = service(store, girl=girl)
        approval = store.policy.m3_approval
        store.policy = store.policy.model_copy(
            update={
                "m3_approval": approval.model_copy(
                    update={"subsystems": approval.subsystems | {"plays"}}
                )
            }
        )
        worker, gateway = GameWorker(game), Gateway()
    with store.transaction() as c:
        canon = state(game)
        canon.world = initial()
        canon = place(place(canon, 2), 3)
        game.event(c, 1, "actual-battle-positions", "synthetic.state", canon)
    svc = BattleService(store)
    data = svc.preview(PLAYER, 900)
    actor = next(x for x in data["actors"] if x["ref"]["entity"] == "2")
    target = next(x for x in data["actors"] if x["ref"]["entity"] == "3")
    declaration = Declaration.model_validate_json(
        __import__("json").dumps(
            dict(
                play="all_out_assault",
                actor=actor["ref"],
                target=target["ref"],
                attacking_asset=actor["assets"][0]["id"],
                target_asset=target["assets"][0]["id"],
                actor_sha256=actor["sha256"],
                target_sha256=target["sha256"],
                account="Actual opening in the current battlefield",
            )
        )
    )
    return game, worker, gateway, svc, data, declaration


def confirm(svc, game, data, declaration):
    offered = svc.propose(PLAYER, str(uuid4()), data["revision"], 900, declaration)
    svc.confirm(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        offered["id"],
        opening=True,
        reach=True,
        outside_permission=False,
        indirect=False,
        evidence="The real opening and range",
    )
    return offered["id"]


def test_actual_owner_proposes_adjudicator_confirms_then_exact_source_prepares_without_rng(ledger):
    game, _, _, svc, data, declaration = prepared(ledger)
    identity = confirm(svc, game, data, declaration)
    with ledger.engine.connect() as c:
        canon = state(game)
        scene = game.scene(c, 900)
        value = PlayInput(
            play="all_out_assault",
            heat=0,
            target_actor=declaration.target,
            attacking_asset=declaration.attacking_asset,
            target_asset=declaration.target_asset,
            battle_context=identity,
            context="Actual opening",
            trigger_confirmed=True,
            piloting=True,
        )
        meta = prepare(game, c, PLAYER, canon, scene, value)
    assert meta["actor"] == declaration.actor.model_dump(mode="json")
    assert meta["target"] == declaration.target.model_dump(mode="json")
    assert meta["modifier"] == 0 and game.dice.calls == 0


def test_declaration_cannot_be_forged_or_reviewed_by_target_human(ledger):
    game, _, _, svc, data, declaration = prepared(ledger)
    with pytest.raises(WorkflowError, match="original actor"):
        svc.propose(OTHER, "wrong-proposer", data["revision"], 900, declaration)
    offered = svc.propose(PLAYER, "owned-offer", data["revision"], 900, declaration)
    before = state(game)
    with pytest.raises(WorkflowError, match="adjudicator"):
        svc.confirm(
            OTHER,
            "not-gm",
            before.revision,
            offered["id"],
            opening=True,
            reach=True,
            outside_permission=True,
            indirect=True,
            evidence="Not my decision",
        )
    assert state(game) == before and game.dice.calls == 0


def test_changed_actual_resource_is_rejected_before_dice_and_replay_does_not_duplicate_context(
    ledger,
):
    game, _, _, svc, data, declaration = prepared(ledger)
    result = svc.propose(PLAYER, "proposal-once", data["revision"], 900, declaration)
    assert svc.propose(PLAYER, "proposal-once", data["revision"], 900, declaration) == result
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["3"].assets[0].damaged = True
        game.event(c, 3, "actual-target-damage", "synthetic.state", canon)
    with pytest.raises(WorkflowError, match="STALE_BATTLE"):
        svc.confirm(
            ADMIN,
            "stale-review",
            state(game).revision,
            result["id"],
            opening=True,
            reach=True,
            outside_permission=False,
            indirect=False,
            evidence="Old opening",
        )
    assert game.dice.calls == 0


def test_confirmed_source_context_can_roll_once_and_unknown_reach_is_not_assumed(ledger):
    game, _, _, svc, data, declaration = prepared(ledger)
    identity = confirm(svc, game, data, declaration)
    with ledger.engine.connect() as c:
        canon = state(game)
        action = {"id": str(uuid4()), "data": {"battle": {"context": identity}}}
        pre_roll(game, c, canon, action)
        assert action["data"]["battle"]["roll_event"]
        with pytest.raises(WorkflowError, match="already rolled"):
            pre_roll(game, c, canon, action)
    assert game.dice.calls == 0


def test_safety_pause_blocks_real_context_mutation_but_preserves_private_read(ledger):
    game, _, _, svc, data, declaration = prepared(ledger)
    ledger.safety(OTHER, "pause-battle", ledger.status(OTHER)["revision"], pause=True)
    assert svc.preview(PLAYER, 900)["scene"] == data["scene"]
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        svc.propose(PLAYER, "paused-proposal", data["revision"], 900, declaration)
    assert game.dice.calls == 0
