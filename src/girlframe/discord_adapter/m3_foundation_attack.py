"""Private controls for the original Foundation attack and human ruling."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_foundation_attack import FoundationAttackService


async def open_attack(
    interaction: discord.Interaction, service: FoundationAttackService, identity: str
) -> None:
    channel = int(interaction.channel_id or 0)
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    status = {
        "destroyed": "The base was destroyed.",
        "averted": "The original Cadre stopped the attack.",
        None: "The original attack awaits resolution."
        if data["attempted"]
        else "The original Pilot can act in the base scene.",
    }[data["result"]]
    text = "\n\n".join(x for x in (status, discord.utils.escape_mentions(data["account"])) if x)
    if not data["choices"]:
        await reply(interaction, text)
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.act,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            channel,
            values["choice"][0],
            values["account"],
        )
        return (
            "The original attempt is recorded."
            if result["decision"] == "attempt"
            else "The base attack is resolved."
        )

    await NativeForm(
        interaction.user.id,
        "Foundation attack on the base",
        text,
        [
            Field("choice", "Your action", data["choices"]),
            Field("account", "What happened?", paragraph=True),
        ],
        submit,
    ).present(interaction)
