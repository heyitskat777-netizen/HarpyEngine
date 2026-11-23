"""Perform the actual Rebel pass through the private native Inbox."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_world import coordinates
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_rebel_strafe import StrafeService


async def open_strafe(
    interaction: discord.Interaction, service: StrafeService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    mode = data["mode"]
    if not mode:
        await reply(interaction, data["account"] or "The original Rebel pass is pending.")
        return
    fields = []
    if mode == "perform":
        if not data["positions"] or not data["assets"]:
            await reply(
                interaction,
                "Recover the actual piloted Frame and a route beside the original base.",
            )
            return
        cells = tuple(f"{x},{y}" for x, y in data["positions"])
        fields += [
            Field(
                "destination",
                "Which adjacent square does the Frame reach?",
                tuple((x, x) for x in cells),
            ),
            Field("asset", "Which functional Frame Asset fires?", data["assets"]),
        ]
    prompt = {
        "propose": "Describe the actual occupied cockpit at the current position",
        "approve": "Confirm the proposed physical facts",
        "perform": "Describe the actual strafing pass",
    }[mode]
    fields.append(Field("account", prompt, paragraph=True))

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.act,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            mode,
            values["account"],
            channel=interaction.channel_id if mode == "perform" else None,
            destination=coordinates(values["destination"][0]) if mode == "perform" else None,
            asset=values["asset"][0] if mode == "perform" else None,
        )
        if result["state"] == "resolved":
            return "The original Frame's strafing pass is recorded."
        return "The original cockpit facts are recorded."

    await NativeForm(
        viewer.user_id, "Rebel pass near " + data["base"], data["account"], fields, submit
    ).present(interaction)
