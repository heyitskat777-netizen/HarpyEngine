"""Actual placed vehicle facts remain separate from Pilot/NPC identities."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_vehicles import VehicleService


async def open_vehicles(interaction: discord.Interaction, service: VehicleService) -> None:
    data = await asyncio.to_thread(
        service.menu, viewer_from_interaction(interaction), int(interaction.channel_id or 0)
    )
    text = "Saved regular vehicles: " + (
        "; ".join(
            x["name"] + " · " + x["occupancy"] + (" · destroyed" if x["destroyed"] else "")
            for x in data["vehicles"]
        )
        or "none"
    )
    if not data["can_assess"]:
        await reply(interaction, text)
        return
    fields = [
        Field("name", "Actual regular vehicle name"),
        Field("description", "Actual vehicle facts (not a Vital Frame)", paragraph=True),
        Field(
            "x",
            "Actual X",
            tuple((str(x), str(x)) for x in range(data["minimum"][0], data["maximum"][0] + 1)),
        ),
        Field(
            "y",
            "Actual Y",
            tuple((str(y), str(y)) for y in range(data["minimum"][1], data["maximum"][1] + 1)),
        ),
        Field(
            "occupancy",
            "Confirmed occupancy",
            (
                ("empty", "Actually empty"),
                ("occupied", "Occupied; occupant effects are separate"),
                ("unknown", "Unknown; no occupant outcome assumed"),
            ),
        ),
    ]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.assess,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            data["channel"],
            values["name"],
            values["description"],
            (int(values["x"][0]), int(values["y"][0])),
            values["occupancy"][0],
        )
        return (
            "Actual regular-vehicle facts saved. Crushing destroys the object; "
            "any harm, escape or other effects on people require their separate actual source."
        )

    form = NativeForm(interaction.user.id, "Assess an actual regular vehicle", text, fields, submit)
    await reply(interaction, form.text(), form)
