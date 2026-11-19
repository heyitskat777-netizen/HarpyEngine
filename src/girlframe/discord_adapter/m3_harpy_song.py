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
    if not data["targets"]:
        await reply(
            interaction, "No Girl without an existing Bond is in audible reach for this move."
        )
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
        return "The Girl’s original private response is pending."

    fields = [
        Field("target", "Original Girl without a Bond", tuple(data["targets"].items())),
        Field("account", "Describe your audible broadcast", paragraph=True),
    ]
    form = NativeForm(
        interaction.user.id, TITLE, "Choose the actual Girl who hears you.", fields, submit
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
            accept=values["choice"][0] == "step",
            account=values["account"],
        )
        return "Your original response is saved."

    fields = [
        Field(
            "choice", "Your response", (("step", "Step toward the Harpy"), ("decline", "Decline"))
        ),
        Field("account", "Describe what your Girl does", paragraph=True),
    ]
    form = NativeForm(interaction.user.id, TITLE, data["account"], fields, submit)
    await reply(interaction, form.text(), form)
