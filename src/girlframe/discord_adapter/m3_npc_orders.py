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
            interaction,
            "None of your actual scene roles has this original source of order authority.",
        )
        return
    voices = {
        ref.token: (ref, item["label"])
        for item in data.get("voices", ())
        for ref in (ActorRef.model_validate(item["ref"]),)
    }

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
            voice=voices[values["voice"][0]][0] if values.get("voice") else None,
        )
        return "The order is saved. The original recipient owns its response. " + str(
            result["action_id"]
        )

    form = NativeForm(
        interaction.user.id,
        "Echoes of Old Command" if origin_kind == "harpy_echoes" else "NPC direct order",
        "Choose the actual issuer with the original saved order authority.\n\n" + instruction,
        [
            Field(
                "issuer",
                "Actual original issuer",
                tuple(
                    (ActorRef.model_validate(x["ref"]).token, x["label"]) for x in data["issuers"]
                ),
            ),
            *(
                [
                    Field(
                        "voice",
                        "Fictional voice to imitate",
                        tuple((key, label) for key, (_ref, label) in voices.items()),
                        0,
                        required=False,
                    )
                ]
                if voices
                else []
            ),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
