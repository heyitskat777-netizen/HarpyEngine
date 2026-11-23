"""Review the original private concealment grant or a witnessed effect."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_void_privacy import ConcealmentService


async def open_concealment(
    interaction: discord.Interaction, service: ConcealmentService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    result = await asyncio.to_thread(service.view, viewer, identity)
    if grant := result["grant"]:
        await reply(
            interaction,
            "Your Void gain went unnoticed."
            if grant.used_event
            else "Your next Void gain is concealed.",
        )
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.arm,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            result["revision"],
            result["game_revision"],
        )
        return "Your next Void gain is concealed. Its treatment still applies."

    form = NativeForm(
        viewer.user_id,
        "Conceal your next Void gain",
        "This applies once to your current Handler.",
        [Field("confirm", "Confirm the Endgame effect", (("confirm", "Conceal the next gain"),))],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_void_notice(
    interaction: discord.Interaction, service: ConcealmentService, identity: str
) -> None:
    await asyncio.to_thread(service.observed, viewer_from_interaction(interaction), identity)
    await reply(interaction, "Your Girl saw the Handler gain Void in the original scene.")
