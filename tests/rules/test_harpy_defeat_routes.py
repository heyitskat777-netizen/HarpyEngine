"""Mandatory actual Harpy Defeat resumes through Inbox and shared native choice dispatch."""

import asyncio

from test_harpy_defeat import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick
from test_mission_ui import current

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.services.inbox import InboxService


def test_real_harpy_defeat_source_inbox_starts_in_original_scene_then_native_tags_and_results(
    ledger,
):
    _, game, worker, gateway, _, work, _ = ready(ledger)
    before = state(game).sheets["2"].model_dump_json()
    inbox = InboxService(ledger)
    row = next(x for x in inbox.items(PLAYER) if x.identity == work)
    assert row.task == "m3_harpy_task:harpy_defeat" and row.incoming

    async def start():
        caller = current(2, 98901)
        await caller.response.defer(ephemeral=True)
        await InboxView(inbox, 2).route(caller, row)
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values["confirm"] = ("yes",)
        response = current(2, 98902)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args

    asyncio.run(start())
    tick(worker, gateway, 3)
    for index, viewer in enumerate((ADMIN, PLAYER, OTHER)):
        choice = next(x for x in game.choices(viewer) if x["kind"] == "tag_window")
        decision = game.decision(viewer, choice["id"])
        assert decision["harpy_defeat"]

        async def pass_tag(viewer=viewer, choice=choice, index=index):
            caller = current(viewer.user_id, 98910 + index * 2)
            await caller.response.defer(ephemeral=True)
            await open_choice(caller, game, choice["id"])
            form = caller.edit_original_response.call_args.kwargs["view"]
            assert isinstance(form, NativeForm) and form.title != "Respond to Play"
            form.values["mode"] = ("pass",)
            await form.confirm.callback(current(viewer.user_id, 98911 + index * 2))
            assert form.completed

        asyncio.run(pass_tag())
    result = next(x for x in game.choices(PLAYER) if x["kind"] == "harpy_defeat_select")

    async def view_result():
        caller = current(2, 98931)
        await caller.response.defer(ephemeral=True)
        await open_choice(caller, game, result["id"])
        menu = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(menu, Picker) and set(dict(menu.options)) == {"message", "rift"}
        assert not await menu.interaction_check(current(3))

    asyncio.run(view_result())
    assert state(game).sheets["2"].model_dump_json() == before and game.dice.calls == 1
    assert not any(x.identity == work for x in inbox.items(PLAYER))
