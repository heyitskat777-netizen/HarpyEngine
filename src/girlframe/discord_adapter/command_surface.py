"""Identify retired HarpyEngine slash commands without changing other registrations."""

import discord
from discord import app_commands

RETIRED_GUILD_COMMANDS = frozenset(
    (
        "battle",
        "campaign",
        "campaign_status",
        "character",
        "choice",
        "facilitator",
        "frame_core",
        "girl",
        "health",
        "help",
        "ledger",
        "mission",
        "play",
        "roll",
        "safety",
        "server",
        "sheet",
        "shelving",
        "session-zero",
        "start",
    )
)


def is_retired_guild_slash(command: app_commands.AppCommand) -> bool:
    return (
        command.type == discord.AppCommandType.chat_input and command.name in RETIRED_GUILD_COMMANDS
    )


async def retire_guild_slash_commands(
    tree: app_commands.CommandTree[discord.Client], guild: discord.Object
) -> tuple[str, ...]:
    """Delete only named legacy guild entries. Treat parallel deletion as success."""
    removed = []
    for command in await tree.fetch_commands(guild=guild):
        if is_retired_guild_slash(command):
            try:
                await command.delete()
            except discord.NotFound:
                pass
            removed.append(command.name)
    return tuple(sorted(removed))
