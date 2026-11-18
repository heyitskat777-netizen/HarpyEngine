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
        await reply(interaction, "This source's civic outcome was already recorded.")
        return
    if data["waits_for_mission"]:
        await reply(interaction, "Reopen after the next mission dispatches.")
        return
    engagement = data["address_during_mission"]

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
        return (
            "The mission's actual response to this protest is recorded."
            if engagement
            else "Actual civic order is restored. Physical damage and other causes remain."
        )

    form = NativeForm(
        interaction.user.id,
        ("Address protest: " if engagement else "Restore order: ") + data["city"],
        "After play, record the next mission's actual response."
        if engagement
        else "After play, describe the established restoration of order.",
        [
            Field("method", "What did the Cadre do?", paragraph=True),
            Field("result", "What happened as a result?", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
