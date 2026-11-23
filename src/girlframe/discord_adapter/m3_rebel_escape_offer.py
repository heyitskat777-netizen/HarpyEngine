"""Native private composition and readback of the Rebel escape offer."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_rebel_escape_offer import EscapeOfferService


async def open_offer(
    interaction: discord.Interaction, service: EscapeOfferService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if data["delivered"]:
        await reply(interaction, data["account"])
        return
    if not data["recipients"]:
        await reply(interaction, "Recover an eligible original Girl before making the offer.")
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.send,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            values["recipient"][0],
            values["account"],
        )
        return "Your offer is available in that Girl's private Inbox."

    await NativeForm(
        interaction.user.id,
        "Make the Rebel's escape offer",
        "Send the actual offer privately. The recipient chooses how to respond.",
        [
            Field("recipient", "Original Girl contacted", tuple(data["recipients"].items())),
            Field("account", "What do you actually offer?", paragraph=True),
        ],
        submit,
    ).present(interaction)
