"""Native private replacement after the original Isolation Protocol trigger."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_chained_isolation import IsolationService


async def open_isolation(
    interaction: discord.Interaction,
    service: IsolationService,
    identity: str,
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    choices: tuple[tuple[str, str], ...] = (
        ("tag", "Give a Tag"),
        ("pass", "Pass"),
        *((key, "Damage " + name) for key, name in data["assets"].items()),
    )
    if data["order_available"]:
        choices += (("order", "Order her to come to my side"),)

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.decide,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            values["choice"][0],
            tag=values.get("tag", ""),
        )
        return "The original replacement is saved."

    form = NativeForm(
        interaction.user.id,
        "Isolation Protocol",
        "The actual Bond was blocked. Choose one available printed replacement or pass.",
        [
            Field("choice", "Your original decision", choices),
            Field("tag", "Original Tag label if chosen", required=False),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
