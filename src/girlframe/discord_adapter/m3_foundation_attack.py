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
        "struck": "The actual strike and its consequences are recorded.",
        None: "The original attack awaits resolution."
        if data["attempted"]
        else "The original Pilot can act in the target's scene.",
    }[data["result"]]
    if data["awaiting_consequences"]:
        status = "The actual strike landed. Finish any required response in the private Inbox."
    text = "\n\n".join(
        x
        for x in (
            discord.utils.escape_mentions(data["target"]),
            status,
            discord.utils.escape_mentions(data["account"]),
        )
        if x
    )
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
            (values.get("asset") or (None,))[0],
        )
        return {
            "attempt": "The original attempt is recorded.",
            "strike": "The strike is recorded. Check the private Inbox for required responses.",
        }.get(result["decision"], "The original attack is resolved.")

    fields = [Field("choice", "Your action", data["choices"])]
    if data["assets"]:
        fields.append(Field("asset", "Actual struck Asset", data["assets"]))
    fields.append(Field("account", "What happened?", paragraph=True))
    await NativeForm(
        interaction.user.id,
        "Original Foundation attack",
        text,
        fields,
        submit,
    ).present(interaction)
