"""An actual intelligence inquiry and its role-scoped native review."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_npc_intelligence import IntelligenceService


async def open_inquiry(
    interaction: discord.Interaction, service: IntelligenceService, channel: int, actor: ActorRef
) -> None:
    data = await asyncio.to_thread(
        service.menu, viewer_from_interaction(interaction), channel, actor
    )
    if not data["targets"]:
        await reply(interaction, "No eligible original NPC is present for this inquiry.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.ask,
            viewer_from_interaction(current),
            str(current.id),
            channel,
            actor,
            data["revision"],
            values["target"][0],
            values["account"],
        )
        return "Your actual inquiry awaits the human facilitator’s private finding."

    form = NativeForm(
        interaction.user.id,
        "Investigate a concealed affiliation",
        "Choose an actual local subject.",
        [
            Field("target", "Original subject", tuple(data["targets"].items())),
            Field("account", "Describe how your Agent investigates", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_inquiry_result(
    interaction: discord.Interaction, service: IntelligenceService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if data["step"] == "report":
        await reply(
            interaction,
            "**Discovered affiliation**\n" + clean(data["learned"]) + "\n" + clean(data["finding"]),
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        choice = values["fact"][0]
        await asyncio.to_thread(
            service.review,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            choice.removeprefix("faction/") if choice.startswith("faction/") else None,
            values["finding"],
        )
        return "The original inquiry’s result is recorded."

    options = (
        *((f"faction/{key}", label) for key, label in data["factions"].items()),
        ("none", "No verified discovery"),
    )
    form = NativeForm(
        interaction.user.id,
        "Review an Intelligence Agent inquiry",
        clean(data["inquiry"]),
        [
            Field("fact", "Actual result", options),
            Field("finding", "Describe evidence limited to this finding", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
