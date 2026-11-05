"""Real Guard-inflicted Broken authority leads to an actual typed NPC order/refusal."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_alpha_brutalize import guard_rolled
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_npc_orders import open_order
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_alpha import conditions
from girlframe.services.m3_npc_orders import NpcOrderService
from girlframe.services.onboarding import WorkflowError


def test_actual_npc_order_native_receive_real_mid_disobey_removes_only_original_broken(
    ledger, tmp_path, monkeypatch
):
    game, guard, npc, alpha, worker, gateway = guard_rolled(ledger, tmp_path, monkeypatch, (1, 1))
    answer(game, ADMIN, "alpha_low", options=("counter_broken",))
    pending = next(x for x in game.choices(ADMIN) if x["kind"] == "alpha_counter_play")
    data = guard.counter(ADMIN, alpha, pending["id"])
    guard.perform_counter(
        ADMIN,
        str(uuid4()),
        alpha,
        pending["id"],
        data["revision"],
        "interpose",
        "The actual Guard steps into the Alpha's way",
    )
    answer(game, PLAYER, "alpha_npc_mercy", options=("spare",))
    tick(worker, gateway, 5)
    original = state(game)
    recipient = current_ref(original, 2)
    assert conditions(original, recipient, npc)
    service = NpcOrderService(game)
    assert not service.preview(PLAYER, 900, 2)["issuers"]
    with pytest.raises(WorkflowError, match="STALE_NPC_ORDER"):
        service.issue(PLAYER, "not-controller", 900, npc, 2, original.revision, "Not my NPC")

    async def issue():
        owner = current(1, 97001)
        owner.channel_id = 900
        await owner.response.defer(ephemeral=True)
        await open_order(owner, service, 2, "Stand down and listen to the actual Guard")
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values["issuer"] = (npc.token,)
        confirmed = current(1, 97002)
        await form.confirm.callback(confirmed)
        assert form.completed, confirmed.edit_original_response.call_args

    asyncio.run(issue())
    with ledger.engine.connect() as c:
        identity = c.scalar(
            sa.select(t.m2["m2_actions"].c.id).where(
                t.m2["m2_actions"].c.campaign_id == ledger.campaign_id,
                sa.func.json_extract(t.m2["m2_actions"].c.body_json, "$.npc_order").is_not(None),
            )
        )
        root = game.action(c, identity)
        source = root["data"]["npc_order"]
        assert source["issuer"] == npc.model_dump(mode="json")
        assert source["target"] == recipient.model_dump(mode="json")
    tick(worker, gateway, 3)

    async def refuse():
        row = next(x for x in game.choices(PLAYER) if x["kind"] == "order_response")
        player = current(2, 97003)
        await player.response.defer(ephemeral=True)
        await open_choice(player, game, row["id"])
        form = player.edit_original_response.call_args.kwargs["view"]
        assert "Actual NPC issuer: Actual Guard" in form.instructions
        form.values["options"] = ("disobey",)
        await form.confirm.callback(current(2, 97004))
        required = next(x for x in game.choices(PLAYER) if x["kind"] == "order_disobey")
        player = current(2, 97005)
        await player.response.defer(ephemeral=True)
        await open_choice(player, game, required["id"])
        form = player.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            play=("disobey_orders",),
            gain=("0",),
            pair_share=("0",),
            heat=("0",),
            piloting=("no",),
            witnessed=("no",),
            context="I actually refuse the original Guard's direct order",
            trigger=("yes",),
        )
        await form.confirm.callback(current(2, 97006))
        assert form.completed

    game.dice.faces = (4, 5)
    asyncio.run(refuse())
    tick(worker, gateway, 3)
    pass_tags(game)

    async def remove():
        row = next(x for x in game.choices(PLAYER) if x["kind"] == "actor_disobey")
        player = current(2, 97007)
        await player.response.defer(ephemeral=True)
        await open_choice(player, game, row["id"])
        form = player.edit_original_response.call_args.kwargs["view"]
        assert "remove_broken" in dict(form.fields[0].options)
        form.values["options"] = ("remove_broken",)
        await form.confirm.callback(current(2, 97008))
        assert form.completed

    asyncio.run(remove())
    answer(game, ADMIN, "handler_disobey", flag=False)
    actual = state(game)
    assert not conditions(actual, recipient, npc)
    assert game.inspect(PLAYER, root["id"])["state"] == "complete"
    assert actual.sheets["2"].heat == original.sheets["2"].heat
    assert game.dice.calls == 2
