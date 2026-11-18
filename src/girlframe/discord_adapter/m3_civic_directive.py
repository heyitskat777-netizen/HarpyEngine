"""Private native controls for the original fictional Director and Handler."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_civic_directive import SUPPORT
from girlframe.services.m3_civic_directive import CivicService


async def open_directive(
    interaction: discord.Interaction, service: CivicService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    order = data["order"]
    issue = data["can_order"]
    if not issue and not data["can_act"]:
        await reply(interaction, order or "The original Director has yet to issue the order.")
        return
    fields = []
    if issue and data["rule"] == SUPPORT:
        if not data["factions"]:
            await reply(interaction, "The order needs an actual active Rebel faction.")
            return
        fields.append(Field("faction", "Which Rebel faction?", tuple(data["factions"])))
    fields.append(
        Field(
            "account",
            "What does the fictional Director actually order?"
            if issue
            else "What public action did the Handler take?",
            paragraph=True,
        )
    )

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.act,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            values["account"],
            issue=issue,
            faction=values["faction"][0] if "faction" in values else None,
        )
        if issue:
            return "The actual order is available in the original Handler's private Inbox."
        return "The original Handler's public action is recorded."

    await NativeForm(
        interaction.user.id,
        "Issue the original civic order" if issue else "Record the Handler's public action",
        f"Original order\n{order}" if order else "The order is delivered privately.",
        fields,
        submit,
    ).present(interaction)
