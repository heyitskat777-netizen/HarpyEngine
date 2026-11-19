"""Spend an advancement on a printed Play from a different Handler book."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.engine.m3_handler_play_state import DRESS_RULE
from girlframe.services.m3_handler_borrowed import BorrowedHandlerService


async def open_borrow(
    interaction: discord.Interaction, service: BorrowedHandlerService, award: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.advancement.view, viewer, award)

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.buy,
            viewer_from_interaction(current),
            str(current.id),
            award,
            data["revision"],
            values["play"][0],
            values["account"],
        )
        return "The borrowed Play is available in your Handler Plays menu."

    await NativeForm(
        viewer.user_id,
        "Take a Play from a different Handler book",
        "Spend this actual held advancement on a printed Play.",
        [
            Field("play", "Printed Play", ((DRESS_RULE, "Dress Them Down (Dogrunner)"),)),
            Field("account", "Your original acquisition account", paragraph=True),
        ],
        submit,
    ).present(interaction)
