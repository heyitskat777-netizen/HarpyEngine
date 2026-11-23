"""Private original contact, intervention and actual delivered defection report."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_rebel_defection import DefectionService


async def open_defection(
    interaction: discord.Interaction, service: DefectionService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    channel = interaction.channel_id
    if data["report"] is not None:
        report = data["report"]
        cell = ", ".join(str(x) for x in report["cell"])
        jobs = ", ".join(str(x).replace("_", " ") for x in report["jobs"])
        await reply(interaction, f"**Defection report**\n{report['name']} · {jobs} · ({cell})")
        return
    if not data["can_stay"] or channel is None:
        await reply(interaction, data["account"] or "The original defection case has ended.")
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.stay,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            channel,
            values["account"],
        )
        return "The contacted NPC has decided to stay after the actual Bond scene."

    form = NativeForm(
        viewer.user_id,
        "Rebel contact",
        data["account"],
        [Field("account", "Why does this NPC decide to stay?", paragraph=True)],
        submit,
    )
    await reply(interaction, form.text(), form)
