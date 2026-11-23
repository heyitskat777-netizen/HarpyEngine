"""Owned native opening and private readback of the laboratory portal."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_void_lab_portal import LabPortalService


async def open_lab(
    interaction: discord.Interaction, service: LabPortalService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.view, viewer, identity)
    if portal := data["portal"]:
        await reply(
            interaction,
            "Stable Voidspace portal at "
            + clean(portal["laboratory"])
            + (
                ". The laboratory is accessible."
                if portal["accessible"]
                else ". The site is unavailable."
            ),
        )
        return
    if not data["sites"]:
        await reply(interaction, "Recover an actual available Foundation laboratory location.")
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.open,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            data["game_revision"],
            values["site"][0],
            values["laboratory"],
            values["account"],
        )
        return "The stable laboratory portal is open. It is recorded on the private map."

    form = NativeForm(
        viewer.user_id,
        "Open a stable Voidspace portal",
        "Use a real Foundation location with a laboratory under your responsibility.",
        [
            Field("site", "Actual laboratory site", data["sites"]),
            Field("laboratory", "Laboratory name"),
            Field("account", "Record the actual opening", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
