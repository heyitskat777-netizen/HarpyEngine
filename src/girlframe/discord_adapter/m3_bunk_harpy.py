"""Original participants' private controls for the High Void bunk encounter."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_bunk_harpy import BunkService


async def open_bunk(
    interaction: discord.Interaction,
    service: BunkService,
    identity: str,
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    subjects = " and ".join(x for x in (data["girl"], data["harpy"]) if x)
    lines = [discord.utils.escape_mentions(subjects) if subjects else "Notice from the bunk"]
    for key in ("appearance", "disclosure"):
        if data[key]:
            lines.append(discord.utils.escape_mentions(data[key]))
    # Render long combined accounts as separate private readbacks.
    readback = "\n\n".join(lines)
    if len(readback) > 1800:
        for line in lines[1:]:
            await interaction.followup.send(
                line, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
            )
        readback = lines[0]
    if not data["options"]:
        await reply(interaction, readback)
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            values["choice"][0],
            values["account"],
        )
        if result["stage"] == "appear":
            return "The appearance is available to the original Girl."
        return "The Handler can read the actual notice in their private Inbox."

    await NativeForm(
        interaction.user.id,
        "Private bunk encounter",
        readback,
        [
            Field("choice", "Your action", data["options"]),
            Field("account", "What actually happens?", paragraph=True),
        ],
        submit,
    ).present(interaction)
