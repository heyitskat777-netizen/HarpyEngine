"""Original Handler and Director controls for a private leak and public response."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_cadre_leak import LeakService


async def open_leak(
    interaction: discord.Interaction,
    service: LeakService,
    identity: str,
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if data["complete"] or not data["options"]:
        await reply(
            interaction,
            "This incident is resolved."
            if data["complete"]
            else "The original incident still needs actual deaths or the Directors' demand.",
        )
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        action = values["action"][0]
        await asyncio.to_thread(
            service.act,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            action,
            values["account"],
        )
        if action == "apologize":
            return "Your actual apology is available in the campaign's Inbox bulletin."
        if action == "demand":
            return "The original Handler received the demand privately."
        return "The original parties' deaths are verified."

    prompt = (
        "Original demand\n" + data["demand"] + "\nYour submitted apology will be public."
        if data["demand"]
        else "Resolve the actual follow-up to the original incident."
    )
    await NativeForm(
        interaction.user.id,
        "Original leaked incident",
        prompt,
        [
            Field("action", "Which actual action are you taking?", data["options"]),
            Field("account", "Your actual statement or reviewed outcome", paragraph=True),
        ],
        submit,
    ).present(interaction)
