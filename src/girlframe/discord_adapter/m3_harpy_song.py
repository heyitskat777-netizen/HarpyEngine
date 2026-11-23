"""Use the Harpy advancement in the native cast and private Inbox."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_harpy_song import HarpySongService

TITLE = "A Song of Love Lost"


async def open_song(
    interaction: discord.Interaction,
    service: HarpySongService,
    channel: int,
    actor: ActorRef,
) -> None:
    data = await asyncio.to_thread(
        service.options, viewer_from_interaction(interaction), channel, actor
    )
    targets = dict(data["targets"])
    if data["handler"]:
        targets["handler"] = "Make the Handler flinch"
    if data["crowd"]:
        targets["crowd"] = "Draw the local NPCs toward you"
    if not targets:
        await reply(interaction, "No supported recipient is in audible reach for this move.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.act,
            viewer_from_interaction(current),
            str(current.id),
            channel,
            actor,
            data["revision"],
            values["target"][0],
            values["account"],
        )
        return "The original recipient’s private response is pending."

    fields = [
        Field("target", "Actual broadcast outcome", tuple(targets.items())),
        Field("account", "Describe your audible broadcast", paragraph=True),
    ]
    form = NativeForm(
        interaction.user.id, TITLE, "Choose the actual recipient who hears you.", fields, submit
    )
    await reply(interaction, form.text(), form)


async def open_song_response(
    interaction: discord.Interaction,
    service: HarpySongService,
    identity: str,
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            accept=values["choice"][0] == "accept",
            account=values["account"],
        )
        return "Your original response is saved."

    label = {
        "handler": "Flinch",
        "girl": "Step toward the Harpy",
        "crowd": "Verify the crowd’s approach",
    }[data["option"]]
    fields = [
        Field("choice", "Your response", (("accept", label), ("decline", "Decline"))),
        Field("account", "Describe the actual response", paragraph=True),
    ]
    form = NativeForm(interaction.user.id, TITLE, data["account"], fields, submit)
    await reply(interaction, form.text(), form)
