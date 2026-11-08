"""One actual native Class purchase, reviewed privately before the two-Permission payment."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_untouchable import UntouchableService
from girlframe.services.onboarding import WorkflowError


async def open_purchase(interaction: discord.Interaction, service: UntouchableService) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction))
    if not data["available"]:
        raise WorkflowError("No reviewed Untouchable acquisition is available")
    if data["suspended"]:
        await reply(
            interaction, "This Class Requisition is suspended. Restore its original paid source."
        )
        return
    if data["owned"]:
        await reply(
            interaction,
            "Untouchable Frame is acquired for your current Frame. "
            "In Engage, choose an own unmarked Tag instead of the printed Asset damage.",
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
            f"Untouchable Frame acquired for {data['price']} Permissions."
            " Choose its Tag option in Engage."
        )

    await NativeForm(
        interaction.user.id,
        f"Untouchable Frame — {data['kind'].replace('_', ' ').title()}, "
        f"{data['price']} Permissions",
        "Source-owned Class Requisition. In Engage, mark your unmarked Tag "
        "instead of damaging an Asset.",
        (
            [Field("donor", "Choose the actual donor Frame", tuple((x, x) for x in data["donors"]))]
            if data["donors"]
            else []
        )
        + [Field("account", "Record the actual acquisition", paragraph=True)],
        submit,
    ).present(interaction)
