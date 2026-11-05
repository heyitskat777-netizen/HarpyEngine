"""Actual Handler-owned NPC role/source completion, without a new body or PC alias."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_am_reset import FactoryResetService


async def open_reset(
    interaction: discord.Interaction, service: FactoryResetService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.complete,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["job"][0],
            values["account"],
        )
        return (
            "The original AM is now the actual NPC under your control. "
            "Her same body, real hardware and history remain; old PC authority has ended."
        )

    form = NativeForm(
        viewer.user_id,
        "Actual AM factory reset",
        f"Original scene <#{data['channel']}>. {data['callsign']} has four actual Limiters. "
        "As the actual Handler, take this same-person NPC and choose her factual printed role. "
        "This changes no physical location, creates no new body or gear, "
        "and erases no extra memory.",
        [
            Field(
                "job",
                "Actual printed NPC role",
                tuple((x, x.replace("_", " ").title()) for x in data["jobs"]),
            ),
            Field(
                "account",
                "Your actual reset and factual role; you take control of this NPC",
                paragraph=True,
            ),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
