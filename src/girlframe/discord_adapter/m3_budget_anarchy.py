"""Actual civic result controls preserve source blockage and physical damage."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_budget_anarchy import AnarchyService


async def open_anarchy(
    interaction: discord.Interaction, service: AnarchyService, identity: str
) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    if data["restored"]:
        await reply(interaction, "This source's civic order was already restored.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.restore,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["method"],
            values["result"],
        )
        return "Actual civic order is restored. Physical damage and other causes remain."

    form = NativeForm(
        interaction.user.id,
        "Restore order: " + data["city"],
        "After play, describe how order was restored. This clears the city's anarchy "
        "and preserves its physical damage and any other blockers.",
        [
            Field("method", "What actually brought order?", paragraph=True),
            Field("result", "What established that order was restored?", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
