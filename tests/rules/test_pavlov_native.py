"""Actual acquired Pavlov may be invoked in a native Keep; ordinary Plays need no claim."""

import asyncio

import pytest
from test_enforcer_requisitions import approved, buy
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, tick
from test_mission_ui import current
from test_requisition_service import ready

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m2_ui import open_choice, open_play
from girlframe.engine.m3_enforcer_requisitions import PAVLOV


@pytest.mark.parametrize("invoke", [False, True])
def test_real_acquired_optional_native_pavlov_preserves_normal_keep_and_one_receipt(
    ledger, tmp_path, monkeypatch, invoke
):
    _, game = ready(ledger, frame="THE ENFORCER")
    service = approved(ledger, game, tmp_path, monkeypatch)
    buy(service, PAVLOV)
    game.dice.faces = (6, 6)

    async def declare():
        caller = current(2, 931001)
        caller.channel_id = 900
        await caller.response.defer(ephemeral=True)
        await open_play(caller, game)
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        condition = next(x for x in form.fields if x.key == "obeying_orders")
        assert condition.required is False
        form.values.update(
            play=("keep_your_head",),
            context="Actual source threat with an optional acquired rule",
            gain=("0",),
            pair_share=("0",),
            heat=("0",),
            piloting=("no",),
            witnessed=("no",),
            trigger=("yes",),
        )
        if invoke:
            form.values.update(
                obeying_orders=("yes",),
                order_account="Actually obeying the current evacuation instruction",
            )
        await form.confirm.callback(current(2, 931002))
        assert form.completed

    asyncio.run(declare())
    with ledger.engine.connect() as c:
        action = game.action(c, game.lock(c, 900)["action_id"])
        identity = action["id"]
        assert action["data"]["enforcer_keep"]["available"] is invoke
        assert action["data"]["receipt"] is None
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    choice = next(x for x in game.choices(PLAYER) if x["kind"] == "actor_keep")

    async def choose():
        caller = current(2, 931003)
        await caller.response.defer(ephemeral=True)
        await open_choice(caller, game, choice["id"])
        form = caller.edit_original_response.call_args.kwargs["view"]
        keys = {x.key for x in form.fields}
        assert ("fields.pavlov_good_soldier" in keys) is invoke
        form.values["text"] = "Actual high Keep result"
        if invoke:
            form.values["fields.pavlov_good_soldier"] = ("yes",)
        await form.confirm.callback(current(2, 931004))
        assert form.completed

    asyncio.run(choose())
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual source outcome is enough")
    result = game.inspect(PLAYER, identity)
    assert result["state"] == "complete" and game.dice.calls == 1
    assert ("good_soldier" in result["result"]["positive"]) is invoke
