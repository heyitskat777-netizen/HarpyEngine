"""Explicit original-caster review before revising an unapplied resource selection."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.services.m3_mockingbird_revision import SexRevisionService


async def open_revision(
    interaction: discord.Interaction, service: SexRevisionService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.revise,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
        )
        return (
            "Uncommitted selection superseded. Reopen the actual owned choice; "
            "the original receipt and spent resources remain unchanged."
        )

    await NativeForm(
        interaction.user.id,
        "Revise an uncommitted selection",
        "This cannot undo actual corruption, treatment, Bond changes "
        "or any other committed effect. "
        "Other participants' proposed descriptions will need new owned source decisions.",
        [
            Field(
                "confirm",
                "Revise only these unapplied choices",
                (("yes", "Review and revise selection"),),
            )
        ],
        submit,
    ).present(interaction)
