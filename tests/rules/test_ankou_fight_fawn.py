"""Actual combat damage produces a private, single-use Fight/Fawn choice."""

from uuid import uuid4

import pytest
from test_ankou import buy, ready
from test_battle_service import assault_declaration, confirm
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick

from girlframe.engine import m3_ankou as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.services.inbox import InboxService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_ankou import AnkouService, prove_roll_modifiers
from girlframe.services.m3_battle import BattleService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.onboarding import WorkflowError


def assault(game, battle):
    data = battle.preview(PLAYER, 900)
    declaration = assault_declaration(data)
    context = confirm(battle, game, data, declaration)
    return PlayInput(
        play="all_out_assault",
        target_actor=declaration.target,
        attacking_asset=declaration.attacking_asset,
        target_asset=declaration.target_asset,
        battle_context=context,
        context=declaration.account,
        trigger_confirmed=True,
        piloting=True,
        heat=0,
    )


@pytest.mark.parametrize("option", ["fight", "fawn"])
def test_damage_creates_owned_fight_fawn_and_only_matching_roll_consumes_it(
    ledger, tmp_path, monkeypatch, option
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    permissions = state(game).sheets["2"].permissions
    buy(controls, rules.FIGHT)
    assert state(game).sheets["2"].permissions == permissions - 2
    battle = BattleService(ledger)
    battle.game = game

    def play(prepared, faces):
        game.dice.faces = faces
        identity = game.begin(
            PLAYER, str(uuid4()), 900, state(game).sheets["2"].revision, prepared
        )["action_id"]
        tick(worker, gateway, 3)
        pass_tags(game)
        return identity

    attack = assault(game, battle)
    source = play(attack, (1, 1))
    assert not rules.records(state(game), rules.FightFawn)
    asset = next(x for x in state(game).sheets["2"].assets if x.id != attack.attacking_asset)
    answer(game, OTHER, "battle_low_damage", fields={"asset": asset.id})
    damaged = state(game)
    assert next(x for x in damaged.sheets["2"].assets if x.id == asset.id).damaged
    task = next(x for x in rules.records(damaged, rules.Task) if x.kind == "fight_fawn")
    assert task.source_action == source and task.source_asset == asset.id
    assert task.target == attack.target_actor and task.controller == PLAYER.user_id
    grant = next(x for x in damaged.handler_plays if x.source_action == source)
    HandlerPlayService(ledger).submit(
        ADMIN,
        "fight-fawn-brief",
        grant.id,
        damaged.revision,
        "brief",
        Effect(kind="brief", account="The actual Handler gives tactical information"),
    )
    tick(worker, gateway, 5)

    reopened = AnkouService(GameService(ledger, dice=game.dice))
    inbox = InboxService(ledger)
    assert any(x.identity == task.id and x.incoming for x in inbox.items(PLAYER))
    assert not any(x.identity == task.id and x.incoming for x in inbox.items(OTHER))
    saved = state(game)
    reply = (task.id, option, "I respond to the actual damage and its original source")
    with pytest.raises(WorkflowError):
        reopened.choose_task(OTHER, "wrong-fight-fawn", saved.revision, *reply)
    with pytest.raises(WorkflowError, match="STALE_ANKOU"):
        reopened.choose_task(PLAYER, "stale-fight-fawn", saved.revision - 1, *reply)
    assert state(game) == saved
    args = (PLAYER, "owned-fight-fawn", saved.revision, *reply)
    result = reopened.choose_task(*args)
    assert reopened.choose_task(*args) == result
    selected = state(game)
    with pytest.raises(WorkflowError):
        reopened.choose_task(PLAYER, "extra-fight-fawn", selected.revision, *reply)
    token = rules.get(selected, rules.FightFawn, task.id)
    assert token.target == attack.target_actor and token.used_action is None
    assert state(game) == selected and game.dice.calls == 1

    prepared = (
        assault(game, battle)
        if option == "fight"
        else PlayInput(
            play="flirt",
            target=OTHER.user_id,
            context="I seek the attention of the Pilot who actually hurt me",
            trigger_confirmed=True,
            heat=0,
        )
    )
    roll = play(prepared, (4, 4))
    used = state(game)
    assert rules.get(used, rules.FightFawn, task.id).used_action == roll
    with ledger.engine.connect() as c:
        action = game.action(c, roll)
        assert prove_roll_modifiers(game, c, used, action) == [{"source": task.id, "amount": 1}]
    receipt = game.inspect(PLAYER, roll)["receipt"]
    assert receipt["pre_total"] == 9 and game.dice.calls == 2
    source_modifiers = [
        modifier for modifier in receipt["pre_modifiers"] if modifier["source"] == task.id
    ]
    assert source_modifiers == [{"source": task.id, "amount": 1}]
    assert game.roll(PLAYER, "fight-fawn-replay", roll)["receipt"] == receipt
    assert game.dice.calls == 2
