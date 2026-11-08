"""Select the actual NPC inflictor as issuer; never use their controller's other role."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_npc_orders import Origin
from girlframe.services.m3_npc_orders import NpcOrderService


async def open_order(
    interaction: discord.Interaction,
    service: NpcOrderService,
    target: int,
    instruction: str,
    *,
    origin_kind: Origin = "broken",
) -> None:
    channel = int(interaction.channel_id or 0)
    data = await asyncio.to_thread(
        service.preview,
        viewer_from_interaction(interaction),
        channel,
        target,
        origin_kind=origin_kind,
    )
    if not data["issuers"]:
        await reply(
            interaction, "No actual NPC you control has this original source of order authority."
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        issuer = next(
            x
            for x in data["issuers"]
            if ActorRef.model_validate(x["ref"]).token == values["issuer"][0]
        )
        result = await asyncio.to_thread(
            service.issue,
            viewer_from_interaction(current),
            str(current.id),
            channel,
            ActorRef.model_validate(issuer["ref"]),
            target,
            data["revision"],
            instruction,
            origin_kind=origin_kind,
        )
        return "Actual NPC order saved; the original recipient owns its response. " + str(
            result["action_id"]
        )

    form = NativeForm(
        interaction.user.id,
        "NPC: direct order",
        "Choose the actual NPC with the original saved order authority. Direct order: "
        + instruction,
        [
            Field(
                "issuer",
                "Actual original NPC issuer",
                tuple(
                    (ActorRef.model_validate(x["ref"]).token, x["label"]) for x in data["issuers"]
                ),
            )
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
