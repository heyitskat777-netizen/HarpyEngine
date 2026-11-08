"""One existing Vatgrown entry point for actual Investors, learning and Doll controls."""

from typing import Any

import discord

from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m2_game import GameService


async def open_vatgrown_menu(interaction: discord.Interaction, game: GameService) -> None:
    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        if values["area"][0] == "doll":
            from girlframe.discord_adapter.m3_vatgrown import open_vatgrown
            from girlframe.services.m3_vatgrown import DollService

            await open_vatgrown(current, DollService(game))
        elif values["area"][0] == "dna":
            from girlframe.discord_adapter.m3_vatgrown_dna import open_vatgrown_dna
            from girlframe.services.m3_vatgrown_dna import VatgrownDNAService

            await open_vatgrown_dna(current, VatgrownDNAService(game))
        else:
            from girlframe.discord_adapter.m3_vatgrown_plays import open_vatgrown_plays
            from girlframe.services.m3_vatgrown_plays import VatgrownPlaysService

            await open_vatgrown_plays(current, VatgrownPlaysService(game))
        return None

    view = NativeForm(
        interaction.user.id,
        "Vatgrown",
        "Choose your private controls.",
        [
            Field(
                "area",
                "Your controls",
                (
                    ("doll", "Unassuming Doll"),
                    ("investors", "Investors, learning and program rules"),
                    ("dna", "DNA basis and actual first comparison"),
                ),
            )
        ],
        choose,
    )
    await reply(interaction, view.text(), view)
