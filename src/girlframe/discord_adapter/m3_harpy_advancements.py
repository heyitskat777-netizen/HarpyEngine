"""Private controls for the original Harpy's advancement."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_harpy_advancements import SPARROWS
from girlframe.services.m3_harpy_advancements import HarpyAdvancementService


async def open_advancement(
    interaction: discord.Interaction, service: HarpyAdvancementService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    summary = f"Your Harpy has used {len(data['learned'])} of {data['slots']} advancement slots."
    if SPARROWS in data["learned"]:
        summary += " Sparrows is available in your Keep Your Head and Engage the Enemy Plays."
    if not data["available"]:
        await reply(interaction, summary)
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.select,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            values["advancement"][0],
        )
        return "Sparrows Led You Over the Black Earth is recorded for your Harpy."

    await NativeForm(
        interaction.user.id,
        "Harpy advancements",
        summary,
        [
            Field(
                "advancement",
                "Choose your advancement",
                ((SPARROWS, "Sparrows Led You Over the Black Earth"),),
            )
        ],
        submit,
    ).present(interaction)
