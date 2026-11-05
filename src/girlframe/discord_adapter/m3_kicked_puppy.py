"""Native LEGION acquisition and explicit zero-Heat Flirt alternative."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_kicked_puppy import KickedPuppyService
from girlframe.services.onboarding import WorkflowError


async def fields(interaction: discord.Interaction, service: KickedPuppyService) -> list[Field]:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction))
    if not data["available"] or not data["owned"]:
        return []
    return [
        Field(
            "kicked_puppy_basis",
            "Flirt only: use damaged Girl Assets (Heat must be 0)",
            (("heat", "Use ordinary Heat"), ("damaged", "Use damaged Girl Assets; spend no Heat")),
            minimum=0,
            required=False,
        )
    ]


def damaged_basis(values: dict[str, Any]) -> bool:
    return values.get("kicked_puppy_basis") == ("damaged",)


async def open_purchase(interaction: discord.Interaction, service: KickedPuppyService) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction))
    if not data["available"]:
        raise WorkflowError("No reviewed native LEGION Kicked Puppy acquisition is available")
    if data["owned"]:
        await reply(
            interaction,
            "Kicked Puppy is acquired. In Flirt you may use damaged Girl Assets "
            "instead of Heat, mark Tags given by that original target, "
            "and ask how they want to care for you.",
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
        )
        return "Kicked Puppy acquired for two Permissions. Its choices appear in Flirt."

    await NativeForm(
        interaction.user.id,
        "Kicked Puppy — native LEGION, 2 Permissions",
        "Use Flirt for the alternate basis, original target-given Tag and care question.",
        [Field("account", "Record your actual acquisition", paragraph=True)],
        submit,
    ).present(interaction)
