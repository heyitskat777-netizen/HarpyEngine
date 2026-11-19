"""The original Rebel opens the attack from the actual mission scene."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_rebel_ambush import AmbushService, HuntService


async def open_ambush(
    interaction: discord.Interaction,
    service: AmbushService,
    identity: str,
) -> None:
    channel = int(interaction.channel_id or 0)
    data = await asyncio.to_thread(
        service.get, viewer_from_interaction(interaction), identity, channel
    )
    if data["complete"]:
        await reply(interaction, "The original mission and ambush are complete.")
        return
    if data["opened"]:
        await reply(interaction, "Use the original scene's battle control to resolve the Assault.")
        return
    if not data["targets"]:
        await reply(
            interaction, "The original Rebel can open the attack in the actual mission scene."
        )
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.open,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            channel,
            values["target"][0],
            values["account"],
        )
        return (
            "The opening is recorded. Declare the Assault against this Girl in the battle control."
        )

    await NativeForm(
        interaction.user.id,
        "Open the original ambush",
        "Choose an original mission participant you are attempting to capture.",
        [
            Field("target", "Original Girl", data["targets"]),
            Field("account", "Describe your actual ambush", paragraph=True),
        ],
        submit,
    ).present(interaction)


async def open_hunt(
    interaction: discord.Interaction,
    service: HuntService,
    identity: str,
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    status = "The original pursuit has ended." if data["ended"] else "The pursuit remains active."
    text = status + f" Resolved attempts: {data['attempts']}."
    if data["proposal"]:
        text += "\n\n" + discord.utils.escape_mentions(data["proposal"])
    if not data["choices"]:
        await reply(interaction, text)
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
        return (
            "The original pursuit has ended." if result["ended"] else "The pursuit remains active."
        )

    await NativeForm(
        interaction.user.id,
        "Review the Rebel pursuit",
        text,
        [
            Field("choice", "Your decision", data["choices"]),
            Field("account", "Your own account", paragraph=True),
        ],
        submit,
    ).present(interaction)
