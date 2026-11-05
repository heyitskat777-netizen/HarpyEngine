"""Actual source grants and human GM procedures have private native entry points."""

import asyncio
from unittest.mock import MagicMock

from test_handler_plays import begin, ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m3_missions import register_missions
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.services.inbox import InboxService
from girlframe.services.m3_missions import MissionService


def test_source_grant_routes_only_its_original_chooser_without_making_a_player_reply(ledger):
    svc, game = ready(ledger)
    identity = begin(svc, game)
    inbox = InboxService(ledger)
    own = [x for x in inbox.items(ADMIN) if x.identity == identity]
    assert len(own) == 1 and own[0].task == "m3_handler_play" and own[0].incoming
    assert not any(x.identity == identity for x in inbox.items(PLAYER))
    assert not any(x.identity == identity for x in inbox.items(OTHER))
    before = state(game).model_dump_json()

    async def run():
        caller = current(1, 98601)
        await caller.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(caller, own[0])
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, Picker)
        assert not await form.interaction_check(current(2))

    asyncio.run(run())
    assert state(game).model_dump_json() == before


def test_mission_handler_native_hub_separates_persona_and_actual_human_gm_controls(ledger):
    _, game = ready(ledger)
    tree = MagicMock()
    register_missions(tree, 200, MissionService(ledger))
    group = tree.add_command.call_args.args[0]
    assert len(group.commands) <= 25

    async def run():
        caller = current(1, 98602)
        await group.get_command("handler").callback(caller)
        menu = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(menu, Picker) and set(dict(menu.options)) == {"persona", "plays"}
        await menu.open_item(caller, "plays")
        plays = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(plays, Picker) and "new" in dict(plays.options)

    before = state(game).model_dump_json()
    asyncio.run(run())
    assert state(game).model_dump_json() == before


def test_affected_original_receives_real_handler_information_without_faked_acknowledgment(ledger):
    from girlframe.engine.m3_handler_play_state import Effect

    svc, game = ready(ledger)
    identity = begin(svc, game)
    data = svc.get(ADMIN, identity)
    svc.submit(
        ADMIN,
        "actual-source-brief",
        identity,
        data["game_revision"],
        "brief",
        Effect(kind="brief", account="PRIVATE_ACTUAL_SITUATION"),
    )
    inbox = InboxService(ledger)
    notice = next(x for x in inbox.items(PLAYER) if x.task == "m3_handler_notice")
    assert not notice.incoming and notice.state == "resolved"
    assert not any(x.identity == identity for x in inbox.items(OTHER))
    before = state(game).model_dump_json()

    async def read():
        caller = current(2, 98604)
        await caller.response.defer(ephemeral=True)
        await InboxView(inbox, 2).route(caller, notice)
        assert (
            clean("PRIVATE_ACTUAL_SITUATION")
            in caller.edit_original_response.call_args.kwargs["content"]
        )

    asyncio.run(read())
    assert state(game).model_dump_json() == before
