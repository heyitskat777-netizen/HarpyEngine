"""Actual Harpy Core strike uses its own real resources and source-bound combat pipeline."""

import json
from uuid import uuid4

import pytest
from test_cast_service import change
from test_harpy_actor_plays import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, answer, state, tick
from test_physical_operations import place

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_plays
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_battle_state import Declaration
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_battle import BattleService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def context(store, *, pc_actor=False, faces=(4, 4)):
    plays, game, cast, actor = ready(store, faces=faces, heat=1)
    target = ActorRef(kind="npc", entity="actual-combatant")
    with store.transaction() as c:
        canon = state(game)
        if pc_actor:
            canon = place(canon, 2)
        canon.world = update(
            canon.world,
            npcs=(
                Npc(
                    id=target.entity,
                    name="Actual opponent",
                    controller=3,
                    cell=(0, 0),
                    jobs=("guard",),
                    detail="Actual introduced opponent",
                    revealed=True,
                ),
            ),
        )
        game.event(c, 1, "synthetic-core-target", "synthetic.world", canon)
    change(cast, OTHER, "join", target)
    battles = BattleService(store)
    preview = battles.preview(PLAYER, 900)
    selected = (
        next(x for x in preview["actors"] if x["ref"] == actor.model_dump(mode="json"))
        if not pc_actor
        else next(x for x in preview["actors"] if x["ref"]["kind"] == "pilot" and x["owned"])
    )
    defender = next(x for x in preview["actors"] if x["ref"] == target.model_dump(mode="json"))
    declaration = Declaration.model_validate_json(
        json.dumps(
            dict(
                play="go_for_the_core",
                actor=selected["ref"],
                target=defender["ref"],
                attacking_asset=selected["assets"][0]["id"],
                actor_sha256=selected["sha256"],
                target_sha256=defender["sha256"],
                account="Actual opening for the original decisive strike",
            )
        )
    )
    proposed = battles.propose(PLAYER, str(uuid4()), preview["revision"], 900, declaration)
    battles.confirm(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        proposed["id"],
        opening=True,
        reach=True,
        outside_permission=True,
        indirect=False,
        evidence="The actual opening and reach have been established in the Conversation",
    )
    own = plays.preview(PLAYER, 900, actor)
    prepared = PlayInput(
        play="go_for_the_core",
        heat=0,
        target_actor=target,
        attacking_asset=declaration.attacking_asset,
        battle_context=proposed["id"],
        context=declaration.account,
        trigger_confirmed=True,
        piloting=bool(selected["piloting"]),
    )
    return plays, game, actor, target, own, prepared


def begin(plays, actor, own, prepared):
    return plays.begin(
        PLAYER,
        str(uuid4()),
        900,
        actor,
        own["actor"]["source_sha256"],
        None,
        own["cast_revision"],
        prepared,
    )["action_id"]


def test_actual_harpy_core_mid_kills_actual_npc_without_touching_controllers_pc(
    ledger, monkeypatch
):
    monkeypatch.setattr(m3_plays, "HEAT_IDS", (*m3_plays.HEAT_IDS, "go_for_the_core"))
    plays, game, actor, target, own, prepared = context(ledger)
    original = state(game)
    action = begin(plays, actor, own, prepared)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    for viewer in (ADMIN, PLAYER, OTHER):
        answer(game, viewer, "tag_window", options=("pass",))
    result = game.inspect(PLAYER, action)
    assert result["state"] == "complete" and game.dice.calls == 1
    assert result["receipt"]["pre_total"] == 8
    assert result["receipt"]["pre_modifiers"] == [dict(source="target_undamaged_assets", amount=0)]
    assert not next(x for x in state(game).world.npcs if x.id == target.entity).alive
    assert state(game).sheets == original.sheets
    assert state(game).native_harpies == original.native_harpies
    assert game.roll(PLAYER, "retry-harpy-core", action)["receipt"] == result["receipt"]
    assert game.dice.calls == 1
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_harpy_cannot_pay_for_same_humans_different_declared_actor(ledger, monkeypatch):
    monkeypatch.setattr(m3_plays, "HEAT_IDS", (*m3_plays.HEAT_IDS, "go_for_the_core"))
    plays, game, actor, target, own, prepared = context(ledger, pc_actor=True)
    before = state(game)
    with pytest.raises(WorkflowError, match="this exact Harpy body"):
        begin(plays, actor, own, prepared)
    assert state(game) == before and not game.dice.calls


def test_harpy_core_remains_gated_with_production_heat_play_list(ledger):
    plays, game, actor, target, own, prepared = context(ledger)
    before = state(game)
    with pytest.raises(WorkflowError, match="release-gated"):
        begin(plays, actor, own, prepared)
    assert state(game) == before and not game.dice.calls
