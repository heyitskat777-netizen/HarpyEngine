"""One actual native LEGION acquisition and full-cost smaller-basis Keep workflow."""

import asyncio
import copy
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, start, state, tick
from test_mission_service import service
from test_mission_ui import current

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_receipt_text import expression
from girlframe.discord_adapter.m2_ui import open_play
from girlframe.discord_adapter.m3_dampener import open_purchase
from girlframe.engine import m3_dampener as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_dampener import DampenerService


def test_dampener_five_heat_threshold_and_printed_plus_two_choice(ledger, tmp_path, monkeypatch):
    """Printed p.92 / PDF p.94: spend at least five Heat, choose +2 or +3."""
    _, game = service(ledger, girl="ALPHA", frame="WYVERN 0.4")
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    with ledger.transaction() as c:
        actual = state(game)
        actual.sheets["2"].permissions = 2
        actual.sheets["2"].heat = 5
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_class_resources", actual)
    source = DampenerService(game)
    menu = source.menu(PLAYER)
    purchase = source.buy(
        PLAYER,
        str(uuid4()),
        menu["revision"],
        current_ref(state(game), 2),
        menu["frame"],
        "Actual native Dampener purchase for the printed lower roll basis",
    )
    before = state(game)
    with pytest.raises(ValueError, match="at least five actual Heat"):
        start(game, heat=4, dampener_modifier=2)
    assert state(game) == before and game.dice.calls == 0
    with ledger.engine.connect() as c:
        assert not game.pending_actions(c) and game.lock(c, 900) is None

    game.dice.faces = (2, 3)
    identity = start(game, heat=5, dampener_modifier=2)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    rolled = copy.deepcopy(game.inspect(PLAYER, identity)["receipt"])
    assert rolled["faces"] == [2, 3] and rolled["pre_total"] == 7
    assert rolled["heat"] == 5 and rolled["base_modifier"] == 2
    assert rolled["dampener_purchase"] == purchase["id"]
    assert "2 Dampener Link (5 Heat spent)" in expression(rolled)
    assert state(game).sheets["2"].heat == 0 and game.dice.calls == 1
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough",))
    answer(game, ADMIN, "handler_keep", flag=True, text="The actual lower-basis result is enough")
    final = game.inspect(PLAYER, identity)
    assert final["state"] == "complete" and final["receipt"] == rolled
    assert final["result"]["tier"] == "low" and game.dice.calls == 1
    tick(worker, gateway, 4)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_native_dampener_keeps_full_heat_cost_and_uses_explicit_smaller_basis(
    ledger, tmp_path, monkeypatch
):
    _, game = service(ledger, girl="ALPHA", frame="WYVERN 0.4")
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    with ledger.transaction() as c:
        actual = state(game)
        actual.sheets["2"].permissions = 2
        actual.sheets["2"].heat = 5
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_class_resources", actual)
    source = DampenerService(game)

    async def buy_and_prepare():
        own = current(2, 999401)
        own.channel_id = 900
        await own.response.defer(ephemeral=True)
        await open_purchase(own, source)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(account="Actual native LEGION Dampener Link acquisition")
        await form.confirm.callback(current(2, 999402))
        assert form.completed
        own = current(2, 999403)
        own.channel_id = 900
        await own.response.defer(ephemeral=True)
        await open_play(own, game)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            play=("keep_your_head",),
            heat=("5",),
            dampener_modifier=("3",),
            gain=("0",),
            pair_share=("0",),
            piloting=("no",),
            witnessed=("no",),
            trigger=("yes",),
            context="I keep my expression controlled under actual pressure",
        )
        await form.confirm.callback(current(2, 999404))
        assert form.completed and game.dice.calls == 0

    asyncio.run(buy_and_prepare())
    acquired = state(game)
    receipt = rules.held(acquired, current_ref(acquired, 2))
    assert receipt and acquired.sheets["2"].permissions == 0
    game.dice.faces = (1, 2)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    identity = game.choices(PLAYER)[0]["action_id"]
    rolled = copy.deepcopy(game.inspect(PLAYER, identity)["receipt"])
    assert rolled["faces"] == [1, 2] and rolled["heat"] == 5 and rolled["pre_total"] == 6
    assert rolled["base_modifier"] == 3 and rolled["modifier_source"] == "Dampener Link"
    assert rolled["dampener_purchase"] == receipt.id
    assert "3 Dampener Link (5 Heat spent)" in expression(rolled)
    assert state(game).sheets["2"].heat == 0 and game.dice.calls == 1
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough",))
    answer(
        game, ADMIN, "handler_keep", flag=True, text="The actual composed response is enough here"
    )
    result = game.inspect(PLAYER, identity)
    assert result["state"] == "complete" and result["receipt"] == rolled and game.dice.calls == 1
    tick(worker, gateway, 4)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
