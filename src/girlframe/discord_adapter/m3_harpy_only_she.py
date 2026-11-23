"""The actual Harpy owns the native Only She Matters selection."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_harpy_only_she import OnlySheMattersService


async def open_only_she(
    interaction: discord.Interaction, service: OnlySheMattersService, channel: int, actor: ActorRef
) -> None:
    data = await asyncio.to_thread(
        service.get, viewer_from_interaction(interaction), channel, actor
    )
    targets = {ref.token: (ref, label) for ref, label in data["targets"].items()}
    if not targets:
        await reply(interaction, "There is no eligible ordinary NPC in your actual square.")
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.act,
            viewer_from_interaction(click),
            str(click.id),
            channel,
            data["revision"],
            actor,
            targets[values["target"][0]][0],
            1 if values["heat"] == ("1",) else 2,
            values["account"],
        )
        return "The original NPC's death and your Harpy's Heat are recorded."

    await NativeForm(
        interaction.user.id,
        "Only She Matters",
        "Choose the original NPC in this scene and record the actual outcome.",
        [
            Field(
                "target", "Original NPC", tuple((k, label) for k, (_ref, label) in targets.items())
            ),
            Field("heat", "Heat to gain", (("1", "1 Heat"), ("2", "2 Heat"))),
            Field("account", "What happened?", paragraph=True),
        ],
        submit,
    ).present(interaction)
