"""Private radio delivery and the original Handler's next interaction."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_rebel_taunt import TauntService


async def open_taunt(
    interaction: discord.Interaction, service: TauntService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity, interaction.channel_id)
    mode = data["mode"]
    if not mode:
        await reply(interaction, data["account"])
        return
    fields = [
        Field(
            "account",
            {
                "radio": "What does the Rebel Handler actually transmit?",
                "tag": "How does the original Handler take this taunt?",
                "interact": "Describe the already performed original interaction",
            }[mode],
            paragraph=True,
        ),
    ]
    if mode == "tag":
        fields.append(Field("tag", "Give yourself a Tag"))
    if mode == "interact":
        fields.append(Field("girl", "Which Girl did you interact with?", data["girls"]))

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.act,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            mode,
            values["account"],
            tag=values.get("tag"),
            channel=interaction.channel_id if mode == "interact" else None,
            girl=int(values["girl"][0]) if mode == "interact" else None,
        )
        return {
            "radio": "The original Handler received the radio taunt.",
            "tag": "The original Tag is saved. The next interaction will require Punishment.",
            "interact": "The actual Punishment is available in the Inbox.",
        }[mode]

    await NativeForm(viewer.user_id, "Rebel radio taunt", data["account"], fields, submit).present(
        interaction
    )
