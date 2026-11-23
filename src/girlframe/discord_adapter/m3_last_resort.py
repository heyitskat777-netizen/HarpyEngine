"""Private Last / Resort purchase and original reserve conditions."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_last_resort import LastResortService
from girlframe.services.onboarding import WorkflowError


async def open_purchase(
    interaction: discord.Interaction, service: LastResortService, award: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.options, viewer, award)
    if not data["bases"]:
        raise WorkflowError("Recover an actual operational base under your responsibility")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.buy,
            viewer_from_interaction(current),
            str(current.id),
            award,
            data["revision"],
            values["base"][0],
            values["account"],
        )
        return "Your private Last / Resort reserve is recorded in your Inbox."

    await NativeForm(
        viewer.user_id,
        "Last / Resort",
        "Use this held advancement to reserve the hidden chassis.",
        [
            Field("base", "Actual Base", data["bases"]),
            Field("account", "Your original reserve account", paragraph=True),
        ],
        submit,
    ).present(interaction)


async def open_reserve(
    interaction: discord.Interaction,
    service: LastResortService,
    identity: str,
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), identity)
    info = (
        "Reserve beneath " + clean(data["base"]) + "."
        if data["base_available"]
        else "The original base is unavailable."
    )
    await reply(
        interaction,
        "**Last / Resort**\n"
        + info
        + "\nConfirmed Cadre losses "
        + str(data["confirmed_losses"])
        + " of "
        + str(data["needed"])
        + " required.",
    )
