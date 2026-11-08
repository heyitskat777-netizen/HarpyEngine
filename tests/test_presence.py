"""Lifecycle/reconnect failures must never strand bot shutdown or expose game state."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from test_read_only_bot import CountingSource
from test_read_only_bot import policy as policy_fixture

from girlframe import __version__
from girlframe.discord_adapter.bot import ReadOnlyDiscordBot
from girlframe.services.read_only_bot import ReadOnlyBotService

policy = policy_fixture


def test_ready_and_resume_restore_public_version_without_duplicate_updates(policy):
    async def run():
        async with ReadOnlyDiscordBot(
            policy, ReadOnlyBotService(policy, CountingSource()), None
        ) as bot:
            assert bot.activity.name == f"Starting v{__version__}"
            assert bot.status == discord.Status.idle
            bot.is_ready = MagicMock(return_value=True)
            bot.change_presence = AsyncMock()
            await bot.on_ready()
            await bot.on_ready()
            assert bot.change_presence.await_count == 1
            sent = bot.change_presence.call_args.kwargs
            assert sent["status"] == discord.Status.online
            assert sent["activity"].to_dict() == {
                "type": 4,
                "state": f"Running v{__version__}",
                "name": "Custom Status",
            }
            await bot.on_disconnect()
            assert bot.change_presence.await_count == 1
            await bot.on_resumed()
            assert bot.change_presence.await_count == 2
            assert bot.activity.name == f"Running v{__version__}"

    asyncio.run(run())


@pytest.mark.parametrize("failure", [None, OSError("Synthetic unavailable socket"), TimeoutError()])
def test_restart_presence_failure_still_closes_and_is_idempotent(policy, failure):
    async def run():
        async with ReadOnlyDiscordBot(
            policy, ReadOnlyBotService(policy, CountingSource()), None
        ) as bot:
            bot.is_ready = MagicMock(return_value=True)
            bot.change_presence = AsyncMock(side_effect=failure)
            await bot.close_for_restart()
            assert bot.is_closed()
            sent = bot.change_presence.call_args.kwargs
            assert sent["activity"].name == f"Restarting v{__version__}"
            assert sent["status"] == discord.Status.dnd
            await bot.close()
            assert bot.change_presence.await_count == 1
            await bot.on_resumed()
            assert bot.change_presence.await_count == 1

    asyncio.run(run())


def test_unconnected_close_never_attempts_gateway_presence(policy):
    async def run():
        async with ReadOnlyDiscordBot(
            policy, ReadOnlyBotService(policy, CountingSource()), None
        ) as bot:
            bot.change_presence = AsyncMock()
            await bot.close()
            bot.change_presence.assert_not_awaited()
            assert bot.is_closed()

    asyncio.run(run())
