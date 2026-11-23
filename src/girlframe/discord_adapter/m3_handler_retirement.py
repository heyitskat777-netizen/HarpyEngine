"""The actual original Handler reports the Endgame medal and home privately."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_handler_retirement import RetirementService


async def open_retirement(
    interaction: discord.Interaction, service: RetirementService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.view, viewer, identity)
    if award := data["award"]:
        status = (
            "Retired to " + clean(award.safe_home)
            if award.retired
            else "Retirement follows this Off-Duty period."
        )
        await reply(interaction, clean(award.medal) + " · " + status)
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.award,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            data["game_revision"],
            values["medal"],
            values["home"],
            values["account"],
        )
        return "The medal is awarded. Retirement follows the original Off-Duty period."

    form = NativeForm(
        viewer.user_id,
        "Receive the medal and prepare retirement",
        "Your current duties continue through this Off-Duty period.",
        [
            Field("medal", "Medal awarded"),
            Field("home", "Your home in a safe Quadrant"),
            Field("account", "Record the actual award and retirement", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
