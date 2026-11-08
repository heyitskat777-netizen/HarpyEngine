"""Actual native source and owner-only item choice/history without private leaks."""

import asyncio

from test_contraband_service import ready
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.m3_contraband import open_find
from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.services.inbox import InboxService

ledger = ledger_fixture


def test_native_handler_has_base_but_no_recipient_picker_and_owner_confirms_asset_and_sharing(
    ledger,
):
    svc, effects, game, identity, selector = ready(ledger, apply=False, public=True)

    async def run():
        handler = current(1)
        await handler.response.defer(ephemeral=True)
        await open_effect(handler, effects, identity)
        form = handler.edit_original_response.call_args.kwargs["view"]
        assert {x.key for x in form.fields} == {"target", "account"}
        assert not await form.interaction_check(current(2))
        form.values = {"target": ("base0",), "account": "PRIVATE_SOURCE_RECORD"}
        submitted = current(1, 19401)
        await form.confirm.callback(submitted)
        assert form.completed and selector.calls == 1
        assert (
            state(game).sheets["2"].callsign
            not in submitted.edit_original_response.call_args.kwargs["content"]
        )
        assert not svc.list(ADMIN)
        owner = current(2)
        await owner.response.defer(ephemeral=True)
        await open_find(owner, svc, identity)
        picker = owner.edit_original_response.call_args.kwargs["view"]
        assert not await picker.interaction_check(current(3))
        await picker.open_item(owner, "add")
        choice = owner.edit_original_response.call_args.kwargs["view"]
        assert not await choice.interaction_check(current(3))
        description, account = "D" * 700, "A" * 1200
        choice.values = {
            "name": "PRIVATE_NATIVE_ITEM",
            "description": description,
            "account": account,
            "confirm": ("yes",),
        }
        await choice.confirm.callback(current(2, 19402))
        assert choice.completed and state(game).sheets["2"].assets[-1].concealed
        assert "PRIVATE_NATIVE_ITEM" not in str(game.sheet(ADMIN, 2))
        await open_find(owner, svc, identity)
        history = owner.edit_original_response.call_args.kwargs["view"]
        await history.open_item(owner, "details")
        assert description in owner.edit_original_response.call_args.kwargs["content"]
        await history.open_item(owner, "account")
        assert account in owner.edit_original_response.call_args.kwargs["content"]
        await history.open_item(owner, "share")
        share = owner.edit_original_response.call_args.kwargs["view"]
        assert state(game).sheets["2"].assets[-1].concealed
        share.values = {"confirm": ("yes",)}
        await share.confirm.callback(current(2, 19403))
        assert share.completed and "PRIVATE_NATIVE_ITEM" in str(game.sheet(ADMIN, 2))
        assert account not in str(game.sheet(ADMIN, 2))
        assert selector.calls == 1 and game.dice.calls == 0

    asyncio.run(run())


def test_native_decline_is_an_explicit_owned_decision_and_moves_to_history(ledger):
    svc, _, game, identity, selector = ready(ledger)
    before = state(game).sheets

    async def run():
        owner = current(2)
        await owner.response.defer(ephemeral=True)
        await open_find(owner, svc, identity)
        picker = owner.edit_original_response.call_args.kwargs["view"]
        await picker.open_item(owner, "decline")
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert {x.key for x in form.fields} == {"confirm"}
        assert svc.get(PLAYER, identity)["taken"] is None
        form.values = {"confirm": ("yes",)}
        await form.confirm.callback(current(2, 19404))
        assert form.completed

    asyncio.run(run())
    assert state(game).sheets == before and selector.calls == 1
    item = next(x for x in InboxService(ledger).items(PLAYER) if x.identity == identity)
    assert item.state == "declined" and not item.incoming
