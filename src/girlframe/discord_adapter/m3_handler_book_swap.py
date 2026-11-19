"""Collect the original Handler's book and retained Play choices."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_handler_book_swap import HandlerBookSwapService


async def open_swap(
    interaction: discord.Interaction, service: HandlerBookSwapService, award: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    revision, books, retained = await asyncio.to_thread(service.options, viewer, award)
    if not books or not retained:
        await reply(interaction, "No eligible switch with one retained ability is available.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.swap,
            viewer_from_interaction(current),
            str(current.id),
            award,
            revision,
            values["book"][0],
            values["retain"][0],
            values["account"],
        )
        kept = dict(retained)[result["retained"]]
        return f"Your Handler is now {result['playbook']} and retains {kept}."

    await NativeForm(
        viewer.user_id,
        "Swap Handler playbook",
        "Spend this held advancement to change the active book and keep one Play or advancement.",
        [
            Field("book", "New playbook", books),
            Field("retain", "Retained ability", retained),
            Field("account", "Your account of the change", paragraph=True),
        ],
        submit,
    ).present(interaction)
