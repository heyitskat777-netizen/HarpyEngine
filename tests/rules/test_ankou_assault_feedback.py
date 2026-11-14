"""A real confirmed Assault pauses before dice and retains its own declaration."""

import asyncio
import copy
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ankou_feedback import begin_mark, choose, finish_keep, ready
from test_battle_pipeline import table
from test_battle_service import confirm
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_battle import open_context
from girlframe.engine import m3_ankou_feedback as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_battle_state import Declaration
from girlframe.services.m3_ankou_feedback import prove, prove_loss_source
from girlframe.services.m3_battle import BattleService, feedback_source_binding, pre_roll
from girlframe.services.onboarding import WorkflowError


def actual_assault_source(ledger, tmp_path, monkeypatch):
    _, game, worker, gateway, _, _ = ready(ledger, tmp_path, monkeypatch)
    identities = [x.id for x in state(game).sheets["2"].identities if not x.marked]
    for identity in identities[:-1]:
        game.dice = Dice((4, 4))
        previous = begin_mark(game, identity)
        tick(worker, gateway, 3)
        finish_keep(game, worker, gateway, previous)
    # These are real proposal and human opening/reach confirmations, after the
    # earlier genuine marks. No Feedback, Context or roll is seeded.
    battle = BattleService(ledger)
    battle.game = game
    data = battle.preview(PLAYER, 900)
    actor = next(x for x in data["actors"] if x["ref"]["entity"] == "2")
    target = next(x for x in data["actors"] if x["ref"]["entity"] == "3")
    declaration = Declaration.model_validate(
        dict(
            play="all_out_assault",
            actor=actor["ref"],
            target=target["ref"],
            attacking_asset=actor["assets"][0]["id"],
            target_asset=target["assets"][0]["id"],
            actor_sha256=actor["sha256"],
            target_sha256=target["sha256"],
            account="PRIVATE_ASSAULT_FEEDBACK: take this actual opening against their Asset",
        )
    )
    context = confirm(battle, game, data, declaration)
    game.dice = Dice((4, 4))

    async def start_native():
        interaction = current(PLAYER.user_id, 99701)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_context(interaction, battle, context)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(identity=(identities[-1],), gain=("1",), pair_share=("0",), heat=("1",))
        response = current(PLAYER.user_id, 99702)
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
    assert source.prepared.battle_context == context and game.dice.calls == 0
    assert source.heat_committed == state(game).sheets["2"].heat == 0
    assert game.inspect(PLAYER, action)["receipt"] is None
    assert not any(
        x.get("kind") == "battle_context_used" and x.get("context") == context
        for x in state(game).facts
    )
    with ledger.engine.connect() as c:
        saved = game.action(c, action)
        assert "roll_event" not in saved["data"]["battle"]
        assert source.battle_source == feedback_source_binding(saved["data"]["battle"])
        assert prove(game, c, state(game), source.id) == source
    return game, worker, gateway, action, source, declaration


def finish_assault(game, worker, gateway, action, source, declaration, calls):
    before = state(game).sheets["2"].model_copy(deep=True)
    tick(worker, gateway, 3)
    assert game.dice.calls == calls
    pass_tags(game)
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt["heat"] == 1 and receipt["pre_total"] == 9
    table(game)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert next(
        x for x in state(game).sheets["3"].assets if x.id == declaration.target_asset
    ).damaged
    assert state(game).sheets["2"].heat == before.heat
    assert state(game).sheets["2"].identities == before.identities
    assert game.roll(PLAYER, str(uuid4()), action)["receipt"] == receipt
    assert game.dice.calls == calls
    used = [
        x
        for x in state(game).facts
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
    assert "PRIVATE_ASSAULT" not in json.dumps(gateway.messages)


@pytest.mark.parametrize("given", [True, False])
def test_native_assault_feedback_purpose_retains_original_attack_or_stops_before_dice(
    ledger, tmp_path, monkeypatch, given
):
    game, worker, gateway, action, source, declaration = actual_assault_source(
        ledger, tmp_path, monkeypatch
    )
    target = current_ref(state(game), OTHER.user_id)
    choose(game, "purpose", target)
    answer(
        game,
        OTHER,
        "ankou_feedback_purpose",
        flag=given,
        text="PRIVATE_ASSAULT_PURPOSE: protect the wounded" if given else "I refuse this purpose",
    )
    assert game.dice.calls == 0
    if not given:
        assert is_helpless(state(game), source.actor, target)
        assert rules.get(state(game), source.id).phase == "ended"
        assert game.inspect(PLAYER, action)["state"] == "complete"
        assert game.inspect(PLAYER, action)["receipt"] is None
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
    with ledger.engine.connect() as c:
        saved = game.action(c, action)
        changed = copy.deepcopy(saved)
        changed["data"]["battle"]["attacking_asset"] = "not-the-original-weapon"
        with pytest.raises(WorkflowError, match="original Assault Feedback"):
            pre_roll(game, c, state(game), changed, commit=False)
        stale = state(game).model_copy(deep=True)
        stale.sheets[target.entity].heat += 1
        with pytest.raises(WorkflowError, match="STALE_BATTLE"):
            pre_roll(game, c, stale, saved, commit=False)
        pre_roll(game, c, state(game), saved, commit=False)
    finish_assault(game, worker, gateway, action, source, declaration, 1)


def test_assault_feedback_tear_and_real_reprisal_preserve_original_declaration(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, action, source, declaration = actual_assault_source(
        ledger, tmp_path, monkeypatch
    )
    target = declaration.target
    asset = next(x for x in state(game).sheets["2"].assets if x.family == "frame" and not x.void)
    assert asset.id != declaration.attacking_asset
    choose(game, "tear", target, asset=asset.id)
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
            context="PRIVATE_ASSAULT_REPRISAL: demand their actual name",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_flirt", options=("name",))
    answer(game, OTHER, "target_flirt", text="PRIVATE_ASSAULT_REPRISAL_ANSWER")
    assert game.inspect(PLAYER, child)["state"] == "complete" and game.dice.calls == 1
    value = rules.get(state(game), source.id)
    assert value.phase == "resolved" and value.child == child
    game.dice.faces = (4, 4)
    finish_assault(game, worker, gateway, action, source, declaration, 2)
