"""Native Modular Build acquisition; actual repair replacement lives in Off-Duty recovery."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_modular import ModularService
from girlframe.services.onboarding import WorkflowError


async def open_purchase(interaction: discord.Interaction, service: ModularService) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction))
    if not data["available"]:
        raise WorkflowError("No reviewed native LEGION Modular Build source is available")
    if data["owned"]:
        await reply(
            interaction,
            "Modular Build is acquired: six counted Frame slots. "
            "Actual Off-Duty recovery offers replacement of eligible damaged Frame Assets.",
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.buy,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            ActorRef.model_validate(data["actor"]),
            data["frame"],
            values["account"],
            values["name"],
            values["description"],
        )
        return "Modular Build acquired for two Permissions; your additional Frame Asset is saved."

    await NativeForm(
        interaction.user.id,
        "Modular Build — native LEGION, 2 Permissions",
        "Gain one additional maximum Frame Asset slot and write one actual new Frame Asset. "
        "Free intrinsic Assets remain outside the counted limit.",
        [
            Field("name", "New Frame Asset name"),
            Field("description", "Describe your new Frame Asset", paragraph=True),
            Field("account", "Record your actual acquisition", paragraph=True),
        ],
        submit,
    ).present(interaction)
