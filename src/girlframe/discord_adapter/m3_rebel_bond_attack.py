"""Private controls for the original NPC's attempt and the Cadre's response."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_rebel_bond_attack import AttackService


async def open_betrayal(
    interaction: discord.Interaction, service: AttackService, identity: str
) -> None:
    channel = int(interaction.channel_id or 0)
    data = await asyncio.to_thread(
        service.get, viewer_from_interaction(interaction), identity, channel
    )
    account = discord.utils.escape_mentions(data["account"])
    if data["finished"]:
        await reply(
            interaction, "The original Cadre intervention stopped the attempt.\n\n" + account
        )
        return
    if not data["can_attempt"] and not data["rescues"]:
        await reply(
            interaction,
            "An original Girl must stop the attacker in the original scene.\n\n" + account
            if data["attempted"]
            else "The original NPC's attack is pending in the source scene.",
        )
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.act,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            channel,
            account=values.get("account", ""),
            action=values["rescue"][0] if "rescue" in values else None,
        )
        return (
            "The original Cadre intervention stopped the attempt."
            if result["finished"]
            else "The original Cadre can intervene."
        )

    if data["can_attempt"]:
        fields = [Field("account", "Describe your NPC's actual attempt", paragraph=True)]
        text = "The original Handler and an original Girl must be present in this scene."
    else:
        fields = [Field("rescue", "Original completed intervention", data["rescues"])]
        text = account
    await NativeForm(interaction.user.id, "Private betrayal", text, fields, submit).present(
        interaction
    )
