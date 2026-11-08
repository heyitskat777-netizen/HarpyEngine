"""Actual assassination offers use the existing owned mission lifecycle."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_missions import open_mission
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_budget_assassination import AssassinationService
from girlframe.services.m3_missions import MissionService


async def open_assignment(
    interaction: discord.Interaction, service: AssassinationService, identity: str
) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    missions = MissionService(service.store)
    if data["phase"] == "mission":
        await open_mission(interaction, missions, data["mission"])
        return
    if data["phase"] == "complete":
        await reply(interaction, "This assassination assignment is complete.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            missions.offer,
            viewer_from_interaction(current),
            str(current.id),
            data["objective"],
            data["players"],
            assassination=identity,
        )
        return (
            "Mission offered. Each invited player answers through /mission inbox. Mission `"
            + str(result["id"])
            + "`."
        )

    form = NativeForm(
        interaction.user.id,
        "Assassination assignment",
        data["objective"] + "\nFinish the current Off-Duty period before offering this mission. "
        "Each invited player decides whether to accept.",
        [
            Field(
                "confirm",
                "Offer this real mission to the Cadre",
                (("yes", "Offer the assassination mission"),),
            )
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
