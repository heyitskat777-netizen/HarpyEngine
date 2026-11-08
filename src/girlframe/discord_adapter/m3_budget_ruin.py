"""Original Handler chooses the two real locations lost to Budget."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_budget_ruin import RuinService


async def open_ruin(interaction: discord.Interaction, service: RuinService, identity: str) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    if data["state"] != "pending":
        await reply(interaction, "These two location losses are already saved.")
        return
    if len(data["locations"]) < 2:
        await reply(interaction, "The map needs two actual surviving locations for this Endgame.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.apply,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            data["game_revision"],
            values["locations"],
            values["account"],
        )
        return "Both locations are ruined and saved." + (
            " Losing the last base requires the Handler's outcome review in requests."
            if result["quadrant_loss"]
            else ""
        )

    form = NativeForm(
        interaction.user.id,
        "Budget: two locations fall to ruin",
        "Choose two existing locations. Last-base consequences remain required.",
        [
            Field(
                "locations",
                "Locations",
                tuple((x["id"], x["label"]) for x in data["locations"]),
                minimum=2,
                maximum=2,
            ),
            Field("account", "Describe their ruin", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
