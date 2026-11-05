"""Owned actual Gorgon World-Asset alteration, never a controller Pilot/Frame form."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_gorgon_dormant import GorgonDormantService


async def open_gorgon_dormant(
    interaction: discord.Interaction, service: GorgonDormantService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if data["state"] == "resolved":
        await reply(interaction, "This original Gorgon's actual counter is complete.")
        return
    if not data["can_act"]:
        await reply(
            interaction, "Recover this original creature's actual body/resource source first."
        )
        return
    already = data["already_fully_void"]
    options = (
        (("already_void", "All actual Gorgon Assets are already Void"),)
        if already
        else tuple((x["id"], x["name"]) for x in data["assets"])
    )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            data["game_revision"],
            None if already else values["asset"][0],
            values["description"],
        )
        return "The actual Gorgon's Void is recorded. Resume the original source attack."

    form = NativeForm(
        interaction.user.id,
        "Gorgon: Dormant counter-Void",
        "Alter an actual original World Asset. This creature has no invented Pilot or Frame roll.",
        [
            Field("asset", "Actual original Gorgon resource", options),
            Field(
                "description", "Describe the actual alteration or fully-Void fact", paragraph=True
            ),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
