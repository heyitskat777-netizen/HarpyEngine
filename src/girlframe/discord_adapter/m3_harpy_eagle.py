"""Native cast controls for the original exposed cockpit."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_harpy_eagle import EagleService


async def open_eagle(
    interaction: discord.Interaction,
    service: EagleService,
    channel: int,
    actor: ActorRef,
) -> None:
    data = await asyncio.to_thread(
        service.get, viewer_from_interaction(interaction), channel, actor
    )
    choices = (
        (("release", "Release the original Girl and cockpit"),)
        if data["holding"]
        else tuple(data["targets"].items())
    )
    if not choices:
        await reply(interaction, "There is no actual exposed cockpit with an eligible known Tag.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.act,
            viewer_from_interaction(current),
            str(current.id),
            channel,
            actor,
            data["revision"],
            values["target"][0],
            values["account"],
        )
        return (
            "The original cockpit is held." if result["held"] else "The original Girl is released."
        )

    fields = [
        Field("target", "Actual target and known Tag", choices),
        Field("account", "Describe the actual outcome", paragraph=True),
    ]
    form = NativeForm(
        interaction.user.id,
        "Eagle Cracks the Shell",
        "Use the actual original Harpy, cockpit and source Tag.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)
