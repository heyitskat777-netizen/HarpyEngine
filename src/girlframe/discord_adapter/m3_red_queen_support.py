"""Open real required Court Plays without manufacturing a parent Action."""

import asyncio

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m2_game import GameService
from girlframe.services.m3_red_queen_support import command_view


async def open_mark_child(
    interaction: discord.Interaction, game: GameService, identity: str
) -> None:
    data = await asyncio.to_thread(
        command_view, game, viewer_from_interaction(interaction), identity
    )
    if data["complete"]:
        await reply(interaction, "This actual commanded Play is completed.")
    elif data["action"]:
        from girlframe.discord_adapter.m2_ui import open_pending

        await open_pending(interaction, game)
    elif data["play"] == "all_out_assault":
        from girlframe.discord_adapter.m3_battle import open_declaration
        from girlframe.services.m3_battle import BattleService

        await open_declaration(interaction, BattleService(game.store), parent=data["parent"])
    else:
        from girlframe.discord_adapter.m2_ui import open_play

        await open_play(interaction, game, parent=data["parent"], _pilot=True)
