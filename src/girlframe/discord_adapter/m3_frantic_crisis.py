"""Private owned Frantic Crisis choices backed by the actual Tag and Strain."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_frantic_crisis import CrisisService


async def open_crisis(
    interaction: discord.Interaction, service: CrisisService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if data["slot"]:
        await reply(interaction, "This Crisis already raised " + clean(data["track"]) + " to High.")
        return
    if not data["available"] or not data["low"]:
        await reply(
            interaction,
            "This Crisis remains pending. Neither of the available Strain raises can apply.",
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.raise_track,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["slot"][0],
            values["track"][0],
        )
        return "The actual Low Strain track is now High."

    form = NativeForm(
        viewer.user_id,
        "Crisis Management",
        "You gained this Tag\n" + clean(data["tag"]),
        [
            Field(
                "slot",
                "Printed consequence",
                tuple(
                    (
                        x,
                        "Raise Low Strain to High. "
                        + ("First use" if x == "raise_first" else "Second use"),
                    )
                    for x in data["available"]
                ),
            ),
            Field("track", "Actual Low Strain", tuple((x, x.title()) for x in data["low"])),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
