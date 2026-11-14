"""One actual original-source Sin of Temptation native private alteration flow."""

import asyncio

import pytest
from test_harpy_bond_void import deepen, owned_choice, prepared
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_harpy_bond_void import open_temptation
from girlframe.engine import m3_harpy_bond_void as rules
from girlframe.services.m3_harpy_bond_void import HarpyBondVoidService
from girlframe.services.onboarding import WorkflowError


def test_actual_saved_sin_choice_native_owner_dropdown_reopen_and_receipt_preserved(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, core, _ = prepared(ledger, tmp_path, monkeypatch)
    action = deepen(game, worker, gateway, core)
    row, effect = owned_choice(game, action)
    receipt = game.inspect(PLAYER, action)["receipt"]
    view = HarpyBondVoidService(game).view(PLAYER, effect.id)
    selected = view["assets"][0]["id"]
    before = state(game)
    text = "SYNTHETIC_PRIVATE_SIN_UI: @everyone this actual Asset grows a glass heartbeat"

    async def exercise():
        for wrong in (ADMIN, OTHER):
            caller = current(wrong.user_id, 998000 + wrong.user_id)
            caller.channel_id = 900
            await caller.response.defer(ephemeral=True)
            with pytest.raises(WorkflowError):
                await open_temptation(caller, game, effect.id)
        original = current(PLAYER.user_id, 998010)
        original.channel_id = 900
        await original.response.defer(ephemeral=True)
        await open_choice(original, game, row["id"])
        form = original.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert not await form.interaction_check(current(OTHER.user_id, 998011))
        actual = next(x for x in form.fields if x.key == "asset")
        assert selected in dict(actual.options)
        form.values.update(asset=(selected,), account=text)
        saved = current(PLAYER.user_id, 998012)
        saved.channel_id = 900
        await form.confirm.callback(saved)
        assert form.completed, saved.edit_original_response.call_args_list
        reopened = current(PLAYER.user_id, 998013)
        reopened.channel_id = 900
        await reopened.response.defer(ephemeral=True)
        await open_temptation(reopened, game, effect.id)
        call = reopened.edit_original_response.call_args.kwargs
        assert "complete" in call["content"] and text in call["content"]
        assert not call["allowed_mentions"].everyone
        assert call.get("view") is None

    asyncio.run(exercise())
    actual = state(game)
    assert rules.get(actual, effect.id).phase == "complete"
    assert actual.sheets["3"] == before.sheets["3"]
    assert actual.sheets["2"].heat == before.sheets["2"].heat
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, action)["receipt"] == receipt and game.dice.calls == 1
    tick(worker, gateway, 5)
    assert text not in str(gateway.messages)
    assert text not in str(ledger.public_export())
