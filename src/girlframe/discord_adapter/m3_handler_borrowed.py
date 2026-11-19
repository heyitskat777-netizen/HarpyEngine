"""Spend an advancement on a printed Play from a different Handler book."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_handler_borrowed import BorrowedHandlerService


async def open_borrow(
    interaction: discord.Interaction, service: BorrowedHandlerService, award: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    revision, choices = await asyncio.to_thread(service.options, viewer, award)
    if not choices:
        await reply(interaction, "No eligible Play from another Handler book is available.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.buy,
            viewer_from_interaction(current),
            str(current.id),
            award,
            revision,
            values["play"][0],
            values["account"],
        )
        return "The borrowed Play is available in your Handler Plays menu."

    await NativeForm(
        viewer.user_id,
        "Take a Play from a different Handler book",
        "Spend this actual held advancement on a printed Play.",
        [
            Field("play", "Printed Play", choices),
            Field("account", "Your original acquisition account", paragraph=True),
        ],
        submit,
    ).present(interaction)
