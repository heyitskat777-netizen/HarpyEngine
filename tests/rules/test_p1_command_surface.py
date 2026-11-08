"""Actual offline SDK registration, including the shared P1 native source entry points."""

import asyncio
from unittest.mock import MagicMock

import discord
from test_ledger import ledger as ledger

from girlframe.discord_adapter.bot import ReadOnlyDiscordBot
from girlframe.services.read_only_bot import ReadOnlyBotService


def test_actual_bot_registers_complete_bounded_private_command_surface(ledger):
    async def run():
        async with ReadOnlyDiscordBot(
            ledger.policy, ReadOnlyBotService(ledger.policy, MagicMock()), None, ledger
        ) as bot:
            guild = discord.Object(id=ledger.policy.guild_id)
            commands = bot.tree.get_commands(guild=guild)
            campaign = bot.tree.get_command("campaign", guild=guild)
            girl = bot.tree.get_command("girl", guild=guild)
            assert campaign.get_command("mentor").parameters
            assert not girl.get_command("mentor").parameters
            for name in ("frame", "move", "vehicle"):
                assert campaign.get_command(name) is not None
            assert bot.tree.get_command("facilitator", guild=guild) is not None
            for name in ("am", "alpha", "princess", "casualty", "vatgrown", "bonded"):
                assert girl.get_command(name) is not None
            assert not bot.tree.get_commands()
            for command in commands:
                if isinstance(command, discord.app_commands.Group):
                    assert len(command.commands) <= 25
                command.to_dict(bot.tree)
            assert not bot.intents.message_content and not bot.intents.members

    asyncio.run(run())
