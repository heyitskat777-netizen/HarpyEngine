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
            frame_area = campaign.get_command("frame").parameters[0]
            assert frame_area.name == "area" and frame_area.default == "frame"
            assert {choice.value for choice in frame_area.choices} == {"frame", "body"}
            mission = bot.tree.get_command("mission", guild=guild)
            position_view = mission.get_command("position").parameters[0]
            assert position_view.name == "view" and position_view.default == "body"
            assert {choice.value for choice in position_view.choices} == {"body", "npc_resources"}
            assert mission.get_command("npc_resources") is None
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
