"""Native direct source spend for one actual new World location."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_location_build import LocationBuildService
from girlframe.services.onboarding import WorkflowError


async def open_build(
    interaction: discord.Interaction, service: LocationBuildService, identity: str | None = None
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), identity)
    if data["historical"]:
        location = data["location"]
        await reply(
            interaction,
            "**Actual new location built**\n"
            + clean(location["name"])
            + " — "
            + location["kind"]
            + " at "
            + str(tuple(location["cell"]))
            + ". One actual Handler advancement spent.",
        )
        return
    if not data["awards"]:
        await reply(interaction, "Building requires one actual held Handler advancement.")
        return

    async def build(current: discord.Interaction, values: dict[str, Any]) -> str:
        try:
            cell = (int(values["x"]), int(values["y"]))
        except ValueError:
            raise WorkflowError("Use actual integer map coordinates") from None
        await asyncio.to_thread(
            service.build,
            viewer_from_interaction(current),
            str(current.id),
            values["award"][0],
            data["revision"],
            values["kind"][0],
            values["name"],
            cell,
            values["account"],
        )
        return "One location built and one advancement spent. Existing world and bodies preserved."

    await NativeForm(
        interaction.user.id,
        "Build a new location",
        "Build one intact Foundation site on a free map square. Existing sites, territory, "
        "actors and positions remain. Map bounds: "
        + str(data["minimum"])
        + " to "
        + str(data["maximum"])
        + ".",
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
                "kind",
                "Actual site kind",
                (("base", "Base"), ("city", "City"), ("important", "Important location")),
            ),
            Field("name", "New location name"),
            Field("x", "Actual map X"),
            Field("y", "Actual map Y"),
            Field("account", "Describe this actual construction", paragraph=True),
        ],
        build,
    ).present(interaction)
