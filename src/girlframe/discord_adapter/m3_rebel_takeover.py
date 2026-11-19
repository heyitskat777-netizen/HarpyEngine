"""Native creation and custody controls for the original takeover."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_world import coordinates
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_rebel_takeover import TakeoverService


async def open_takeover(
    interaction: discord.Interaction, service: TakeoverService, identity: str
) -> None:
    channel = int(interaction.channel_id or 0)
    data = await asyncio.to_thread(
        service.get, viewer_from_interaction(interaction), identity, channel
    )

    if data["setup"]:

        async def organize(click: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.organize,
                viewer_from_interaction(click),
                str(click.id),
                identity,
                data["revision"],
                values["name"],
                values["description"],
                coordinates(values["cell"]),
            )
            return (
                "The new group replaced the old one."
                if result["complete"]
                else "The new group's members can resolve custody in their original scenes."
            )

        await NativeForm(
            interaction.user.id,
            "Write up the new Rebel Group",
            "Give the new group its own name, territory and reason it is more dangerous.",
            [
                Field("name", "Group name"),
                Field("description", "What makes it more dangerous?", paragraph=True),
                Field("cell", "Territory coordinates"),
            ],
            organize,
        ).present(interaction)
        return

    description = f"{clean(data['group'])}. Captured {data['captured']} · Broken {data['broken']}."
    if data["total"] is not None:
        description += f" Original Pilots {data['total']}."
    if data["complete"]:
        await reply(interaction, description + " The former group has been destroyed.")
        return
    if not data["choices"]:
        await reply(
            interaction,
            description + " The original participants can resume together in their scene.",
        )
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.resolve,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            channel,
            values["choice"][0],
            values["account"],
        )
        return "The original consequence is recorded."

    await NativeForm(
        interaction.user.id,
        "Resolve the original takeover",
        description,
        [
            Field("choice", "Original consequence", data["choices"]),
            Field("account", "What happened in your scene?", paragraph=True),
        ],
        submit,
    ).present(interaction)
