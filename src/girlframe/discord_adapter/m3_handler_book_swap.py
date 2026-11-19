"""Collect the original Handler's book and retained Play choices."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.engine.m3_handler_play_state import DRESS_RULE
from girlframe.services.m3_handler_book_swap import HandlerBookSwapService


async def open_swap(
    interaction: discord.Interaction, service: HandlerBookSwapService, award: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.advancement.view, viewer, award)

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.swap,
            viewer_from_interaction(current),
            str(current.id),
            award,
            data["revision"],
            values["book"][0],
            values["retain"][0],
            values["account"],
        )
        return "Your Handler is now Frantic and retains Dress Them Down."

    await NativeForm(
        viewer.user_id,
        "Swap Handler playbook",
        "Spend this held advancement to change the active book and keep one earned Play.",
        [
            Field("book", "New playbook", (("Frantic", "Frantic"),)),
            Field("retain", "Retained Play", ((DRESS_RULE, "Dress Them Down"),)),
            Field("account", "Your account of the change", paragraph=True),
        ],
        submit,
    ).present(interaction)
