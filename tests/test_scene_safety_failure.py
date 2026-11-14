"""Offline scene safety failure guidance; no live Discord or storage connections."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from girlframe.discord_adapter.m2_ui import SceneControls
from girlframe.services import ledger as ledger_module


@pytest.mark.parametrize("failure_at", ["construction", "status", "safety"])
def test_scene_pause_storage_failure_tells_player_to_stop(monkeypatch, caplog, failure_at):
    game = MagicMock()
    game.store.policy.m3_approval = None
    status = MagicMock(return_value={"revision": 7})
    safety = MagicMock()
    ledger = MagicMock(status=status, safety=safety)
    factory = MagicMock(return_value=ledger)
    failing_call = {"construction": factory, "status": status, "safety": safety}[failure_at]
    failing_call.side_effect = RuntimeError("synthetic private database details")
    monkeypatch.setattr(ledger_module, "CampaignLedger", factory)
    interaction = MagicMock()
    interaction.id = 123
    interaction.user.id = 2
    interaction.guild_id = 200
    interaction.response.defer = AsyncMock()
    interaction.response.is_done.return_value = True
    interaction.edit_original_response = AsyncMock()

    async def run():
        controls = SceneControls(game)
        await controls.pause.callback(interaction)

    asyncio.run(run())

    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    interaction.edit_original_response.assert_awaited_once()
    response = interaction.edit_original_response.await_args.kwargs
    assert response["content"] == (
        "Safety request could not be saved. Stop play and contact an administrator."
    )
    assert not response["allowed_mentions"].everyone
    assert not response["allowed_mentions"].users
    assert not response["allowed_mentions"].roles
    interaction.response.send_message.assert_not_called()
    factory.assert_called_once_with(game.store)
    if failure_at == "construction":
        status.assert_not_called()
    else:
        status.assert_called_once()
    if failure_at == "safety":
        safety.assert_called_once_with(status.call_args.args[0], "123", 7, pause=True)
    else:
        safety.assert_not_called()
    assert "Scene safety pause request could not be saved." in caplog.text
    assert "synthetic private database details" not in caplog.text
