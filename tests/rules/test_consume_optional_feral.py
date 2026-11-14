"""Printed low Feral Handler discretion through the real owned native choice."""

import asyncio
from uuid import uuid4

from test_consume import acquire, ready, roll
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.m3_consume import open_choice
from girlframe.engine import m3_consume as rules
from girlframe.engine.m3_actor_bonds import current_ref

ledger = ledger_fixture


def test_low_feral_handler_can_decline_without_tag_or_forced_disobey(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    acquire(controls, rules.FERAL)
    before = state(game)
    actor = current_ref(before, 2)
    action = roll(game, worker, gateway, play="consume_feral", faces=(1, 1), heat=0)
    pending = next(x for x in game.choices(ADMIN) if x["kind"] == "consume_feral")
    source_before = rules.session(state(game), action)
    assert source_before.total < 8 and not source_before.completed_event
    row = game.decision(ADMIN, pending["id"])
    assert dict(row["detail"]["options"]) == {
        "give": "Give the actual Tag",
        "decline": "Do not give a Tag",
    }

    async def decline():
        opened = current(1, uuid4().int % 1000000000)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_choice(opened, game, row)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(2, uuid4().int % 1000000000))
        form.values.update(option=("decline",), account="I do not give her a Tag for this failure")
        submitted = current(1, uuid4().int % 1000000000)
        submitted.channel_id = 900
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        completed = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == completed

    asyncio.run(decline())
    after = state(game)
    source = rules.session(after, action)
    assert source.completed_event
    assert source.roll_event == source_before.roll_event and source.total == source_before.total
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert after.sheets["2"].tags == before.sheets["2"].tags
    assert after.sheets["2"].heat == before.sheets["2"].heat
    assert not rules.feral_effects(after, actor)
    assert not rules.disobey_low(after, actor)
    assert not [x for x in rules.records(after, rules.Reaffirmation) if x.session == action]
    with ledger.transaction() as c:
        saved = game.action(c, action)
        assert saved["data"]["consume"]["feral_tag_declined"]
