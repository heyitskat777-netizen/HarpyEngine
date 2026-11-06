"""Native original Handler restoration of an actual Location with one held award."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_location_rebuild import LocationRebuildService


async def open_rebuild(
    interaction: discord.Interaction, service: LocationRebuildService, identity: str | None = None
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), identity)
    if data["historical"]:
        await reply(
            interaction,
            "**Actual location rebuilt**\n"
            + clean(data["location"])
            + ": "
            + data["before"]
            + " → "
            + data["after"]
            + ". One actual Handler advancement spent.",
        )
        return
    if not data["awards"] or not data["locations"]:
        await reply(
            interaction,
            "Rebuilding requires a held Handler advancement and an existing non-intact location.",
        )
        return

    async def rebuild(current: discord.Interaction, values: dict[str, Any]) -> str:
        location = next(x for x in data["locations"] if x["id"] == values["location"][0])
        await asyncio.to_thread(
            service.rebuild,
            viewer_from_interaction(current),
            str(current.id),
            values["award"][0],
            data["revision"],
            location["id"],
            location["fingerprint"],
            values["account"],
        )
        return "Actual location rebuilt. One advancement spent; existing sources preserved."

    await NativeForm(
        interaction.user.id,
        "Rebuild an actual location",
        "Restore one existing damaged or destroyed location to intact. Its identity, position, "
        "allegiance and real blockers remain. Spend one actual advancement; past losses remain.",
        [
            Field(
                "award",
                "Actual held advancement",
                tuple(
                    (x["id"], x["rule"].replace("strain.void.endgame.", "Void Endgame "))
                    for x in data["awards"]
                ),
            ),
            Field(
                "location",
                "Actual existing location",
                tuple((x["id"], x["label"] + " — " + x["condition"]) for x in data["locations"]),
            ),
            Field("account", "Describe this actual rebuilding", paragraph=True),
        ],
        rebuild,
    ).present(interaction)
