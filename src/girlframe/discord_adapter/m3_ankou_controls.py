"""Optional owned Amygdala selector; its move commits only with the real roll."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field
from girlframe.services.m2_game import GameService
from girlframe.services.m3_ankou_controls import pulse_tags


async def pulse_fields(interaction: discord.Interaction, game: GameService) -> list[Field]:
    tags = await asyncio.to_thread(pulse_tags, game, viewer_from_interaction(interaction))
    return (
        [
            Field(
                "ankou_pulse",
                "Amygdala: Assault, Engage or Beneath only",
                (("none", "Keep your Tags"), *tags),
            )
        ]
        if tags
        else []
    )


def selected_pulse(values: dict[str, Any]) -> str | None:
    chosen = values.get("ankou_pulse", ("none",))
    return str(chosen[0]) if chosen and chosen[0] != "none" else None
