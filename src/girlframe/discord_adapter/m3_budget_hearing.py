"""Native private controls for the Girl and the fictional Director."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_budget_hearing import HearingService


async def open_hearing(
    interaction: discord.Interaction, service: HearingService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    descriptions = [
        f"**{label}**\n{discord.utils.escape_markdown(discord.utils.escape_mentions(data[key]))}"
        for key, label in (
            ("charge", "Accusation"),
            ("defense", "Response"),
            ("finding", "Finding"),
        )
        if data[key]
    ]
    descriptions.append(
        "The accusation was withdrawn."
        if data["phase"] == "dismissed"
        else "The finding requires a human rules decision."
        if data["phase"] == "review"
        else "Each original party owns their own statement."
    )
    readback = "\n\n".join(descriptions)
    # Keep each private response within Discord's message limit, without truncating the evidence.
    if len(readback) > 1800:
        for section in descriptions[:-1]:
            for offset in range(0, len(section), 1800):
                await interaction.followup.send(
                    section[offset : offset + 1800],
                    ephemeral=True,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        readback = descriptions[-1]
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
        if result["phase"] == "review":
            return (
                "Finding saved for human rules review. The required consequence is still pending."
            )
        return "Your statement is saved in the original parties' private hearing."

    await NativeForm(
        interaction.user.id,
        "Review the private hearing",
        readback,
        [
            Field("choice", "Your response", data["options"]),
            Field("account", "Your own statement (up to 1,200 characters)", paragraph=True),
        ],
        submit,
    ).present(interaction)
