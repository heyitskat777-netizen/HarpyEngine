"""Real paid Home and shared cockpit reject an actual Flirt Tag without a new action."""

import asyncio
from uuid import uuid4

import sqlalchemy as sa
from test_home import ITEMS, ready, rescue_guest
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_home import open_effect, open_home
from girlframe.engine import m3_home as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref


def test_actual_home_rejects_genuine_flirt_tag_without_action_or_new_charge(
    ledger, tmp_path, monkeypatch
):
    game, home = ready(ledger, tmp_path, monkeypatch)
    before = state(game)
    actor = current_ref(before, 2)

    async def acquire():
        opened = current(2, int(uuid4().int % 1000000000))
        await opened.response.defer(ephemeral=True)
        await open_home(opened, home)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(items=ITEMS, account="My actual secret Home installation")
        await form.confirm.callback(current(2, int(uuid4().int % 1000000000)))
        assert form.completed

    asyncio.run(acquire())
    paid = rules.held(state(game), actor)
    assert paid and paid.price == 2
    assert state(game).sheets["2"].permissions == before.sheets["2"].permissions - 2
    worker, gateway = rescue_guest(game)
    assert home.menu(PLAYER)["others"]
    game.dice.faces = (6, 6)
    flirt = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="flirt",
            target=3,
            heat=0,
            context="I actually Flirt with the rescued original companion in my cockpit",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "actor_flirt",
        options=("name",),
        fields={"extra": "owe"},
        text="I go too far and genuinely owe the rescued companion",
    )
    answer(game, OTHER, "target_flirt", text="My actual requested name")
    answer(game, OTHER, "flirt_owe_tag", text="Actually named by my rescued companion")
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, flirt)["state"] == "complete"
    before = state(game)
    tag = next(
        x for x in before.sheets["2"].tags if x.label == "Actually named by my rescued companion"
    )
    assert tag.giver_actor == current_ref(before, 3)
    owed = next(
        x
        for x in before.obligations
        if x.kind == "cannot_refuse_until_tag_resolved" and x.details.get("tag") == tag.id
    )
    assert owed.state == "pending"
    assert any(x["id"] == tag.id for x in home.menu(PLAYER)["tags"])
    calls = game.dice.calls
    with ledger.engine.connect() as c:
        actions = c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_actions"]))

    async def reject():
        opened = current(2, int(uuid4().int % 1000000000))
        await opened.response.defer(ephemeral=True)
        await open_effect(opened, home, "reject")
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3, int(uuid4().int % 1000000000)))
        form.values.update(
            other=("3",), tag=(tag.id,), account="This actual Tag no longer defines me"
        )
        await form.confirm.callback(current(2, int(uuid4().int % 1000000000)))
        assert form.completed

    asyncio.run(reject())
    after = state(game)
    assert not any(x.id == tag.id for x in after.sheets["2"].tags)
    assert [x for x in before.sheets["2"].tags if x.id != tag.id] == after.sheets["2"].tags
    assert after.sheets["2"].heat == before.sheets["2"].heat
    assert after.sheets["2"].permissions == before.sheets["2"].permissions
    assert after.placements == before.placements and after.requisitions == before.requisitions
    assert game.dice.calls == calls
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_actions"])) == actions
    assert rules.held(after, actor) == paid
    assert next(x for x in after.obligations if x.id == owed.id).state == "fulfilled"
