"""Original-role controls for the theft, interception and recovery."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_rebel_frame_theft import TheftService


async def open_theft(
    interaction: discord.Interaction, service: TheftService, identity: str
) -> None:
    channel = int(interaction.channel_id or 0)
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if data["returned"]:
        await reply(interaction, "The original Frame is back at the base.")
        return
    if data["stopped"]:
        await reply(interaction, "The original interception stopped the theft.")
        return
    account = discord.utils.escape_mentions(data["account"])
    status = "The original Frame is out of reach." if data["lost"] else "The theft is unresolved."
    detail = "\n\n".join(x for x in (status, account) if x)
    if not (data["choices"] or data["stops"]):
        await reply(interaction, detail)
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.act,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            channel,
            "stop" if "stop" in values else values["choice"][0],
            account=values.get("account", ""),
            action=values["stop"][0] if "stop" in values else None,
        )
        return "Your actual original outcome is saved."

    fields = (
        [Field("stop", "Original completed interception", data["stops"])]
        if data["stops"]
        else [
            Field("choice", "Your owned choice", data["choices"]),
            Field("account", "Describe your actual action", paragraph=True),
        ]
    )
    await NativeForm(interaction.user.id, "Original Frame theft", detail, fields, submit).present(
        interaction
    )
