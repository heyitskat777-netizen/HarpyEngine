"""The real Aggressive controller explicitly takes or declines its immediate extra hit."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_gorgon_aggressive import AggressiveService


async def open_aggressive(
    interaction: discord.Interaction, service: AggressiveService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if data["state"] != "pending":
        await reply(interaction, "This immediate hit choice is already resolved.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        asset = values["asset"][0]
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            data["game_revision"],
            None if asset == "pass" else asset,
            values["account"],
        )
        return (
            "Immediate choice saved. The actual Defeat roll can now use the remaining Girl Assets."
        )

    form = NativeForm(
        interaction.user.id,
        "Aggressive: immediate Girl hit",
        "The Gorgon may damage one Girl Asset after exhausting this Frame, "
        "before Defeat is rolled.",
        [
            Field(
                "asset",
                "Optional immediate hit",
                (("pass", "Decline the extra hit"),)
                + tuple((x["id"], x["name"]) for x in data["assets"]),
            ),
            Field("account", "Describe the Gorgon's actual choice", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
