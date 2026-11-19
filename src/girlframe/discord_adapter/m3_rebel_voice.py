"""Private controls for the original in-fiction voice operator."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_npc_orders import NpcOrderService
from girlframe.services.m3_rebel_voice import VoiceService
from girlframe.services.onboarding import WorkflowError


async def open_voice(
    interaction: discord.Interaction, service: VoiceService, identity: str
) -> None:
    channel = interaction.channel_id or 0
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity, channel)
    ready = data["ready"]
    if ready and not data["girls"]:
        await reply(
            interaction, "Open this private request from a scene with an original Cadre Girl."
        )
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        actor = viewer_from_interaction(click)
        if not ready:
            await asyncio.to_thread(
                service.synthesize,
                actor,
                str(click.id),
                identity,
                data["revision"],
                values["account"],
            )
            return "The voice is ready. Reopen the private card from the intended scene."
        try:
            await asyncio.to_thread(
                NpcOrderService(service.game).issue,
                actor,
                str(click.id),
                channel,
                data["issuer"],
                int(values["girl"][0]),
                data["revision"],
                values["order"],
                origin_kind="rebel_voice",
                source_effect=identity,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
        return "The original Girl can respond through Receive Orders."

    fields = (
        [
            Field("girl", "Original recipient", data["girls"]),
            Field("order", "Direct Order", paragraph=True),
        ]
        if ready
        else [Field("account", "Record the actual voice synthesis", paragraph=True)]
    )
    form = NativeForm(
        viewer.user_id,
        "Private Rebel voice",
        "Only the original controller can use this source.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)
