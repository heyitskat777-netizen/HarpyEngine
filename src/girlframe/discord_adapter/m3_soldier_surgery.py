"""Private choices for the original Soldier's immediate Tag embrace."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_soldier_surgery import SoldierSurgeryService


async def open_soldier_surgery(
    interaction: discord.Interaction,
    service: SoldierSurgeryService,
    identity: str,
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    instructions = "Choose whether the Soldier must immediately embrace the Tag you gave her."
    if data["owner_replaces"]:
        instructions = "Choose which of your eligible Identities the original Tag replaces."
        choices = (
            (("embrace", "Use the open Identity slot"),)
            if data["open_slot"]
            else tuple(data["replacements"].items())
        )
    else:
        choices = (("pass", "Pass"),)
        if data["tag"]:
            choices += (("embrace", "Require immediate embrace"),)
    if data["tag"]:
        instructions += "\nOriginal Tag — " + clean(data["tag"])
    if not choices or data["owner_replaces"] and data["tag"] is None:
        await reply(interaction, "The original Tag or a legal Identity slot needs recovery.")
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.decide,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            values["choice"][0],
        )
        return "Your original choice is saved."

    form = NativeForm(
        viewer.user_id,
        "Simplification Surgery",
        instructions,
        [Field("choice", "Your decision", choices)],
        submit,
    )
    await reply(interaction, form.text(), form)
