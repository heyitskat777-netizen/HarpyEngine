"""Original recipient of the High Void contact chooses their own alteration."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_void_signal import SignalService


async def open_signal(
    interaction: discord.Interaction,
    service: SignalService,
    identity: str,
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if data["gain_event"] is not None:
        await reply(
            interaction, "Your Void alteration is saved. Review any pending transformation."
        )
        return
    if not data["assets"]:
        await reply(interaction, "The Void gain still needs an eligible owned Asset.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.gain,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["asset"][0],
            values["account"],
        )
        if result["state"] == "pending":
            return "Your Void alteration is recorded. Continue the required transformation."
        return "Your chosen Asset gained Void."

    await NativeForm(
        interaction.user.id,
        "Gain Void from the Gorgon's contact",
        "Choose the actual Asset and describe its alteration.",
        [
            Field("asset", "Which of your Assets gains Void?", data["assets"]),
            Field("account", "How does the Void alter it?", paragraph=True),
        ],
        submit,
    ).present(interaction)
