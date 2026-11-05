"""One paid native Priestess Keep: owned Void basis and established terrifying quality."""

import asyncio
import copy
from uuid import uuid4

from test_enforcer_requisitions import approved
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_receipt_text import expression
from girlframe.discord_adapter.m2_ui import open_choice, open_play
from girlframe.discord_adapter.m3_nightmare import open_purchase
from girlframe.engine import m3_nightmare as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_nightmare import NightmareService


def test_native_nightmare_keep_uses_void_without_heat_and_preserves_owned_traits(
    ledger, tmp_path, monkeypatch
):
    _, game = service(ledger, girl="ALPHA", frame="CONSUME")
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    with ledger.transaction() as c:
        actual = state(game)
        actual.sheets["2"].permissions = 2
        actual.sheets["2"].heat = 5
        for family in ("girl", "frame"):
            next(x for x in actual.sheets["2"].assets if x.family == family).void = True
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_class_resources", actual)
    source = NightmareService(game)

    async def buy_and_prepare():
        own = current(2, 999601)
        own.channel_id = 900
        await own.response.defer(ephemeral=True)
        await open_purchase(own, source)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(account="Actual native Priestess Nightmare Core acquisition")
        await form.confirm.callback(current(2, 999602))
        assert form.completed
        own = current(2, 999603)
        own.channel_id = 900
        await own.response.defer(ephemeral=True)
        await open_play(own, game)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert "Nightmare Core" in form.text()
        form.values.update(
            play=("keep_your_head",),
            heat=("0",),
            gain=("0",),
            pair_share=("0",),
            piloting=("no",),
            witnessed=("no",),
            trigger=("yes",),
            context="I keep my head while my actual Void alterations terrify the opposition",
        )
        await form.confirm.callback(current(2, 999604))
        assert form.completed and game.dice.calls == 0

    asyncio.run(buy_and_prepare())
    actual = state(game)
    paid = rules.held(actual, current_ref(actual, 2))
    assert paid and actual.sheets["2"].permissions == 0
    game.dice.faces = (3, 3)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    identity = game.choices(PLAYER)[0]["action_id"]
    raw = copy.deepcopy(game.inspect(PLAYER, identity)["receipt"])
    assert raw["heat"] == 0 and raw["base_modifier"] == 2 and raw["pre_total"] == 8
    assert raw["nightmare_purchase"] == paid.id
    assert "2 Void Assets (Nightmare Core) (no Heat spent)" in expression(raw)
    assert state(game).sheets["2"].heat == 5 and game.dice.calls == 1
    pass_tags(game)

    async def actual_owned_outcomes():
        own = current(2, 999605)
        await own.response.defer(ephemeral=True)
        choice = next(x for x in game.choices(PLAYER) if x["kind"] == "actor_keep")
        await open_choice(own, game, choice["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        assert "always terrifying enough" in form.text()
        form.values.update(options=("tough", "in_control"), denied=("desperate",))
        await form.confirm.callback(current(2, 999606))
        assert form.completed
        handler = current(1, 999607)
        await handler.response.defer(ephemeral=True)
        choice = next(x for x in game.choices(ADMIN) if x["kind"] == "handler_keep")
        await open_choice(handler, game, choice["id"])
        form = handler.edit_original_response.call_args.kwargs["view"]
        form.values.update(flag=("yes",), text="The established terrifying quality is enough here")
        await form.confirm.callback(current(1, 999608))
        assert form.completed

    asyncio.run(actual_owned_outcomes())
    final = game.inspect(PLAYER, identity)
    assert final["state"] == "complete" and final["receipt"] == raw and game.dice.calls == 1
    assert {"terrifying", "tough", "in_control"} <= set(final["result"]["positive"])
    assert final["result"]["negative"] == ["desperate"] and final["result"]["enough"] is True
    assert state(game).sheets["2"].heat == 5
    tick(worker, gateway, 4)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
