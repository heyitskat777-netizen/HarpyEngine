"""Actual native or grafted acquisition and clear Keep cost/basis presentation."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_nightmare import NightmareService
from girlframe.services.onboarding import WorkflowError


async def keep_info(
    interaction: discord.Interaction, service: NightmareService, actor: ActorRef | None = None
) -> dict[str, Any] | None:
    if actor is not None and actor.kind != "pilot":
        return None
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), actor)
    return data if data["available"] and data["owned"] else None


def keep_heat(info: dict[str, Any] | None, available: int) -> tuple[int, ...]:
    return (0,) if info else (available,) if available >= 5 else tuple(range(available + 1))


async def open_purchase(interaction: discord.Interaction, service: NightmareService) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction))
    if not data["available"]:
        raise WorkflowError("No reviewed Nightmare Core acquisition is available")
    if data["suspended"]:
        await reply(interaction, "Nightmare Core is suspended. Restore its original paid source.")
        return
    if data["owned"]:
        await reply(
            interaction,
            "Nightmare Core is acquired. Keep Your Head uses your Void Asset count "
            "instead of Heat, and you are always terrifying enough.",
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
            values["donor"][0] if data["donors"] else None,
        )
        return (
            f"Nightmare Core acquired for {data['price']} Permissions. "
            "Keep uses Void Assets and spends no Heat."
        )

    await NativeForm(
        interaction.user.id,
        f"Nightmare Core — {'native Priestess' if data['price'] == 2 else 'Frame Grafting'}, "
        f"{data['price']} Permissions",
        "Keep Your Head uses owned Void Assets instead of Heat. You are always terrifying enough.",
        (
            [
                Field(
                    "donor",
                    "Choose the Priestess donor Frame",
                    tuple((x, x) for x in data["donors"]),
                )
            ]
            if data["donors"]
            else []
        )
        + [Field("account", "Record your actual acquisition", paragraph=True)],
        submit,
    ).present(interaction)
