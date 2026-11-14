"""Real exposed-Core declarations retain their costs through mandatory Feedback."""

import asyncio
import copy
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ankou_feedback import begin_mark, choose, finish_keep, ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_battle import open_context
from girlframe.engine import m3_ankou_feedback as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_battle_state import Declaration
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.m3_ankou_feedback import prove, prove_loss_source
from girlframe.services.m3_battle import BattleService, feedback_source_binding, pre_roll
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.onboarding import WorkflowError


def actual_core_source(ledger, tmp_path, monkeypatch, *, damaged_weapon=False):
    _, game, worker, gateway, _, _ = ready(ledger, tmp_path, monkeypatch)
    # Only prior ordinary Asset setup is synthetic. Every Identity mark,
    # cockpit entry, exposure, declaration and later consequence is real.
    with ledger.transaction() as c:
        canon = state(game)
        weapon = next(x for x in canon.sheets["2"].assets if x.family == "girl")
        weapon.damaged = damaged_weapon
        game.event(c, 1, str(uuid4()), "synthetic.prior_core_bodies_and_weapon", canon)
    identities = [x.id for x in state(game).sheets["2"].identities if not x.marked]
    for identity in identities[:-1]:
        game.dice = Dice((4, 4))
        previous = begin_mark(game, identity)
        tick(worker, gateway, 3)
        finish_keep(game, worker, gateway, previous)
    physical = PhysicalService(ledger)
    for viewer in (PLAYER, OTHER):
        data = physical.preview(viewer)
        physical.operate(
            viewer,
            str(uuid4()),
            data["game_revision"],
            CockpitAction(
                actor=ActorRef.model_validate(data["actor"]),
                operation="pilot",
                expected_position=data["position_sha256"],
                account="PRIVATE_CORE_BODY: enter and pilot my actual current Frame",
                confirmed=True,
            ),
        )
    battle = BattleService(ledger)
    battle.game = game
    data = battle.preview(PLAYER, 900)
    target = ActorRef.model_validate(
        next(x for x in data["actors"] if x["ref"]["entity"] == "3")["ref"]
    )
    exposed = battle.expose(
        OTHER,
        str(uuid4()),
        state(game).revision,
        target,
        "PRIVATE_CORE_EXPOSURE: I willingly expose this actual occupied Frame Core",
        willing=True,
    )
    assert exposed
    data = battle.preview(PLAYER, 900)
    acting = next(x for x in data["actors"] if x["ref"]["entity"] == "2")
    opposing = next(x for x in data["actors"] if x["ref"]["entity"] == "3")
    declaration = Declaration.model_validate(
        dict(
            play="go_for_the_core",
            actor=acting["ref"],
            target=opposing["ref"],
            attacking_asset=weapon.id,
            actor_sha256=acting["sha256"],
            target_sha256=opposing["sha256"],
            account="PRIVATE_CORE_FEEDBACK: strike the actual exposed original Core",
        )
    )
    offered = battle.propose(PLAYER, str(uuid4()), data["revision"], 900, declaration)
    battle.confirm(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        offered["id"],
        opening=True,
        reach=True,
        outside_permission=False,
        indirect=False,
        core_capability_confirmed=damaged_weapon,
        evidence="The actual weapon can reach and pierce this original exposed Core",
    )
    game.dice = Dice((6, 6))

    async def start_native():
        interaction = current(PLAYER.user_id, 99801)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_context(interaction, battle, offered["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(identity=(identities[-1],), gain=("1",), pair_share=("0",), heat=("1",))
        response = current(PLAYER.user_id, 99802)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list
        with ledger.engine.connect() as c:
            return json.loads(
                c.scalar(
                    sa.select(t.commands.c.outcome_json).where(
                        t.commands.c.campaign_id == ledger.campaign_id,
                        t.commands.c.interaction_key == str(response.id),
                    )
                )
            )["action_id"]

    action = asyncio.run(start_native())
    tick(worker, gateway, 3)
    source = next(x for x in rules.sources(state(game)) if x.action == action)
    assert source.prepared.battle_context == offered["id"] and game.dice.calls == 0
    assert source.heat_committed == state(game).sheets["2"].heat == 0
    assert game.inspect(PLAYER, action)["receipt"] is None
    assert not any(
        x.get("kind") == "battle_context_used" and x.get("context") == offered["id"]
        for x in state(game).facts
    )
    with ledger.engine.connect() as c:
        saved = game.action(c, action)
        meta = saved["data"]["battle"]
        assert "roll_event" not in meta and meta["target_asset"] is None
        assert any(
            x.get("kind") == "battle_frame_exposure" and x.get("event") == meta["source_core"]
            for x in state(game).facts
        )
        assert source.battle_source == feedback_source_binding(meta)
        assert prove(game, c, state(game), source.id) == source
    return game, worker, gateway, action, source, declaration


def finish_core(game, worker, gateway, action, source, declaration, calls):
    before = state(game).sheets["2"].model_copy(deep=True)
    penalty = len([x for x in state(game).sheets["3"].assets if not x.damaged])
    tick(worker, gateway, 3)
    assert game.dice.calls == calls
    pass_tags(game)
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt["heat"] == 1 and receipt["pre_total"] == 13 - penalty
    assert 8 <= receipt["pre_total"] <= 10
    assert game.inspect(PLAYER, action)["state"] == "complete"
    canon = state(game)
    assert "3" not in canon.sheets
    assert canon.career_archives[-1].actor == declaration.target
    assert canon.career_archives[-1].ending == "death"
    assert canon.sheets["2"].heat == before.heat
    assert canon.sheets["2"].identities == before.identities
    assert game.roll(PLAYER, str(uuid4()), action)["receipt"] == receipt
    assert game.dice.calls == calls
    used = [
        x
        for x in canon.facts
        if x.get("kind") == "battle_context_used" and x.get("action") == action
    ]
    assert len(used) == 1 and used[0]["context"] == source.prepared.battle_context
    tick(worker, gateway, 5)
    with game.store.engine.connect() as c:
        saved = game.action(c, action)
        assert feedback_source_binding(saved["data"]["battle"]) == source.battle_source
        assert used[0]["event"] == saved["data"]["battle"]["roll_event"]
        assert prove(game, c, state(game), source.id).receipt == receipt["id"]
        assert game.lock(c, 900)["state"] == "released"
    assert "PRIVATE_CORE" not in json.dumps(gateway.messages)


@pytest.mark.parametrize("given", [True, False])
def test_native_core_feedback_purpose_keeps_actual_exposure_or_stops_before_dice(
    ledger, tmp_path, monkeypatch, given
):
    game, worker, gateway, action, source, declaration = actual_core_source(
        ledger, tmp_path, monkeypatch
    )
    choose(game, "purpose", declaration.target)
    answer(
        game,
        OTHER,
        "ankou_feedback_purpose",
        flag=given,
        text="PRIVATE_CORE_PURPOSE: end this war" if given else "I refuse this purpose",
    )
    assert game.dice.calls == 0
    if not given:
        assert is_helpless(state(game), source.actor, declaration.target)
        assert rules.get(state(game), source.id).phase == "ended"
        assert game.inspect(PLAYER, action)["state"] == "complete"
        assert game.inspect(PLAYER, action)["receipt"] is None and "3" in state(game).sheets
        assert not any(
            x.get("kind") == "battle_context_used" and x.get("action") == action
            for x in state(game).facts
        )
        tick(worker, gateway, 5)
        with ledger.engine.connect() as c:
            assert game.lock(c, 900)["state"] == "released"
        assert game.dice.calls == 0
        return
    replace = next(x.id for x in state(game).sheets["2"].identities if not x.protected)
    answer(game, PLAYER, "ankou_feedback_identity", fields={"replace": replace})
    assert game.inspect(PLAYER, action)["state"] == "ready_to_roll"
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "held"
        saved = game.action(c, action)
        changed = copy.deepcopy(saved)
        changed["data"]["battle"]["source_core"] = "not-the-original-exposure"
        with pytest.raises(WorkflowError, match="original Core Feedback"):
            pre_roll(game, c, state(game), changed, commit=False)
        stale = state(game).model_copy(deep=True)
        stale.facts = [x for x in stale.facts if x.get("kind") != "battle_frame_exposure"]
        with pytest.raises(ValueError, match="Expose the original occupied Frame"):
            pre_roll(game, c, stale, saved, commit=False)
        stale = state(game).model_copy(deep=True)
        stale.sheets["3"].assets[0].damaged = True
        with pytest.raises(WorkflowError, match="STALE_BATTLE"):
            pre_roll(game, c, stale, saved, commit=False)
        pre_roll(game, c, state(game), saved, commit=False)
    finish_core(game, worker, gateway, action, source, declaration, 1)


def test_core_feedback_tear_keeps_confirmed_damaged_weapon_and_real_reprisal(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, action, source, declaration = actual_core_source(
        ledger, tmp_path, monkeypatch, damaged_weapon=True
    )
    asset = next(x for x in state(game).sheets["2"].assets if x.family == "frame" and not x.void)
    choose(game, "tear", declaration.target, asset=asset.id)
    value = rules.get(state(game), source.id)
    assert value.phase == "child" and state(game).sheets["2"].heat == 5
    with ledger.engine.connect() as c:
        loss = prove_loss_source(game, c, state(game), value.choice_event, value.id, value.actor)
        assert loss["in_battle"] is True and loss["source_action"] == action
    game.dice = Dice((1, 2))
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="flirt",
            parent=action,
            source_work=value.id,
            target=OTHER.user_id,
            heat=5,
            context="PRIVATE_CORE_REPRISAL: demand their actual name",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_flirt", options=("name",))
    answer(game, OTHER, "target_flirt", text="PRIVATE_CORE_REPRISAL_ANSWER")
    assert game.inspect(PLAYER, child)["state"] == "complete" and game.dice.calls == 1
    value = rules.get(state(game), source.id)
    assert value.phase == "resolved" and value.child == child
    assert next(
        x for x in state(game).sheets["2"].assets if x.id == declaration.attacking_asset
    ).damaged
    game.dice.faces = (6, 6)
    finish_core(game, worker, gateway, action, source, declaration, 2)
