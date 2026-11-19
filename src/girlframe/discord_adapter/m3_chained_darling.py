"""Native placement and original facilitator review for the Chained Darling."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_chained_darling import ChainedPlacementService

TITLE = "Chained Darling placement"
LABELS = {
    "piloting": "Piloting my actual Frame",
    "inside_frame": "Inside my Frame without piloting",
    "outside_frame": "Outside my own Frame",
}


async def open_chained_placement(
    interaction: discord.Interaction,
    service: ChainedPlacementService,
    channel: int,
    actor: ActorRef,
) -> None:
    data = await asyncio.to_thread(
        service.menu, viewer_from_interaction(interaction), channel, actor
    )
    if not data["modes"]:
        await reply(interaction, "There is no unreviewed placement or cockpit exit to record.")
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.propose,
            viewer_from_interaction(click),
            str(click.id),
            channel,
            actor,
            data["revision"],
            values["mode"][0],
            values["account"],
        )
        return "The original facilitator has a private placement review."

    instructions = (
        "Record your actual current placement."
        if data["initial"]
        else "Record your own exit from your actual Frame."
    )
    form = NativeForm(
        interaction.user.id,
        TITLE,
        instructions,
        [
            Field("mode", "Actual physical position", tuple((x, LABELS[x]) for x in data["modes"])),
            Field("account", "What is happening in the scene", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_chained_review(
    interaction: discord.Interaction,
    service: ChainedPlacementService,
    identity: str,
) -> None:
    data = await asyncio.to_thread(service.review, viewer_from_interaction(interaction), identity)
    instructions = clean(data["actor"]) + " submits " + clean(LABELS[data["mode"]]) + "."
    instructions += "\n" + clean(data["account"])

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.decide,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            values["choice"][0] == "yes",
        )
        return "The original physical review is saved."

    form = NativeForm(
        interaction.user.id,
        TITLE,
        instructions,
        [
            Field("choice", "Actual physical review", (("yes", "Verify"), ("no", "Decline"))),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
