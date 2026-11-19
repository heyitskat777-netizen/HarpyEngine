"""Native controls for the original discoverer and the Handler's Void choice."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_npc_void import MANIFESTATIONS
from girlframe.services.m3_npc_interest import InterestService


async def open_interest(
    interaction: discord.Interaction, service: InterestService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    lines = tuple(x for x in (data["account"], data["seen_tag"]) if x)
    if not data["discover"] and not data["gain"]:
        await reply(interaction, "\n".join(lines) or "The original discovery is pending.")
        return
    discover = data["discover"]
    field = (
        Field("account", "What did the Girl actually observe in this scene?", paragraph=True)
        if discover
        else Field(
            "manifestation",
            "How does the original NPC gain Void?",
            tuple((x, "Void of the " + x) for x in MANIFESTATIONS),
        )
    )

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.act,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            channel=interaction.channel_id if discover else None,
            account=values["account"] if discover else None,
            manifestation=values["manifestation"][0] if not discover else None,
        )
        if result["state"] == "resolved":
            return "The discovery and the NPC's Void gain are recorded."
        return "The original observation is recorded."

    await NativeForm(
        viewer.user_id,
        "Discover an NPC's interest in the Void" if discover else "Apply the NPC's Void gain",
        "\n".join(lines) or "Use the scene where the original encounter actually happened.",
        [field],
        submit,
    ).present(interaction)
