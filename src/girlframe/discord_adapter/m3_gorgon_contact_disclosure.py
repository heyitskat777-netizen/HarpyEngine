"""The original participant can disclose the exact private source to the Handler."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_gorgon_contact_disclosure import FrameContactDisclosureService


async def open_report(
    interaction: discord.Interaction, service: FrameContactDisclosureService, identity: str
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), identity)

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.report,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["scene"][0],
        )
        return "The actual Handler heard your report. Its required Punishment is recorded."

    form = NativeForm(
        interaction.user.id,
        "Disclose your private Gorgon contact",
        "Your original contact stays private until you report it to the Handler. "
        "The printed Punishment becomes due once the Handler hears the report.",
        [
            Field(
                "scene",
                "Open scene with the Handler",
                tuple((scene, f"Scene in channel {channel}") for scene, channel in data["scenes"]),
            )
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
