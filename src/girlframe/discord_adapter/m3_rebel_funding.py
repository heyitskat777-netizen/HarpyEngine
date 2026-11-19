"""A private participation card shares only what its actual actor needs."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_rebel_funding import FundingService


async def open_participation(
    interaction: discord.Interaction, service: FundingService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    channel = int(interaction.channel_id or 0)
    candidates = data["candidates"]
    choices = data["choices"]
    if data["completed"]:
        await reply(interaction, "The original participation is recorded.")
        return
    if not candidates and not choices:
        await reply(
            interaction,
            "The original actor's reply is pending."
            if data["invited"]
            else "Recover an eligible original insurgent actor and controller.",
        )
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.act,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            channel,
            "nominate" if candidates else values["choice"][0],
            nominee=values["nominee"][0] if candidates else None,
            account=values.get("account", ""),
        )
        return "Your private decision is recorded."

    fields = (
        [Field("nominee", "Original insurgent actor", candidates)]
        if candidates
        else [
            Field("choice", "Your decision", choices),
            Field("account", "Your actual role in the event", paragraph=True, required=False),
        ]
    )
    await NativeForm(
        interaction.user.id,
        "Rebellion event participation",
        "Arrange the original actor's part in this event."
        if data["sponsor"]
        else "This invitation concerns your own insurgent character.",
        fields,
        submit,
    ).present(interaction)
