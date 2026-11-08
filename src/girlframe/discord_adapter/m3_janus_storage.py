"""Private stored alterations and one actual Foundation surgery per Off-Duty period."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_janus_storage import StorageService


async def open_storage(interaction: discord.Interaction, service: StorageService) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction))
    text = (
        "\n".join(
            ("Active while plugged: " if x["active"] else "Inactive while unplugged: ")
            + x["description"]
            for x in data["points"]
        )
        or "No actual stored Void points."
    )
    if not data["points"] or not data["periods"]:
        await reply(interaction, text)
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.request,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            values["point"][0],
            values["period"][0],
            values["account"],
        )
        return "Actual Foundation surgical request saved in its reviewer's Inbox."

    await NativeForm(
        interaction.user.id,
        "Void Storage — actual stored points",
        text,
        [
            Field(
                "point",
                "One actual point to remove",
                tuple((x["id"], x["description"][:90]) for x in data["points"]),
            ),
            Field(
                "period", "Your actual Go Off-Duty period", tuple((x, x) for x in data["periods"])
            ),
            Field("account", "Describe the actual surgical request", paragraph=True),
        ],
        submit,
    ).present(interaction)


async def open_surgery(
    interaction: discord.Interaction, service: StorageService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if not data["can_act"]:
        await reply(interaction, "Actual surgery: " + data["work"]["phase"])
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.confirm,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["account"],
        )
        return "One actual stored Void removed. The original Asset is undamaged."

    await NativeForm(
        interaction.user.id,
        "Foundation — actual Void Storage surgery",
        data["work"]["account"] + "\nRecord surgery only after it actually occurs.",
        [Field("account", "Describe the performed surgical removal", paragraph=True)],
        submit,
    ).present(interaction)
