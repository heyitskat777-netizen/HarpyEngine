"""The Harpy's controller links the raid to their actual completed attack."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_harpy_raid import RaidService


async def open_raid(
    interaction: discord.Interaction,
    service: RaidService,
    identity: str,
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    summary = f"{data['base']} · Obsession {data['obsession']}"
    if data["action"] or not data["attacks"]:
        description = (
            "The confirmed Assault is preserved."
            if data["action"]
            else "Play out the original Harpy's Assault against the Cadre at this base."
        )
        await reply(interaction, summary + "\n" + description)
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.finish,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            values["action"][0],
        )
        return "The original raid is recorded. Reopen Off-Duty for any remaining work."

    await NativeForm(
        interaction.user.id,
        "Confirm the Harpy raid and obsession",
        summary,
        [Field("action", "Which actual Assault fulfilled this raid?", data["attacks"])],
        submit,
    ).present(interaction)
