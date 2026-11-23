"""Private Conditioned Hate response and original facilitator confirmation."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_warboy_hate import ConditionedHateService


async def open_conditioned_hate(
    interaction: discord.Interaction, service: ConditionedHateService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if data["review"]:
        text = (
            "Does the original action immediately reaffirm "
            + clean(data["tag"])
            + "?\n"
            + clean(data["account"])
        )
        options = (("yes", "Confirm the actual action"), ("no", "Decline"))
        fields = [Field("choice", "Your decision", options)]
    else:
        text = "Act immediately to reaffirm one of your existing Tags."
        choices = tuple(data["tags"].items())
        if not choices:
            await reply(interaction, "Your Warboy has no available Tag for this response.")
            return
        fields = [
            Field("choice", "Your actual Tag", choices),
            Field("account", "What did your Warboy immediately do?", paragraph=True),
        ]

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        selected = values["choice"][0]
        await asyncio.to_thread(
            service.act,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            tag=None if data["review"] else selected,
            account=values.get("account", ""),
            verify=selected == "yes" if data["review"] else None,
        )
        return "The original Warboy response is saved."

    form = NativeForm(interaction.user.id, "Conditioned Hate", text, fields, submit)
    await reply(interaction, form.text(), form)
