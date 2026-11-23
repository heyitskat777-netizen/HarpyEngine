"""Private delivery and reuse of an actual Benevolent Gorgon Play."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_benevolent_contact import PLAYS
from girlframe.services.m3_benevolent_contact import ContactService


async def open_contact(
    interaction: discord.Interaction, service: ContactService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    channel = interaction.channel_id or 0
    data = await asyncio.to_thread(service.get, viewer, identity, channel)
    title = dict(PLAYS)[data["play"]]
    if not data["targets"]:
        await reply(interaction, title + "\n" + data["account"])
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.repeat,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            values["girl"][0],
            channel,
            values["account"],
        )
        return "The original Gorgon's Play is recorded for its actual addressee."

    form = NativeForm(
        viewer.user_id,
        title,
        "Previous delivery\n" + data["account"],
        [
            Field("girl", "Girl to address in this scene", data["targets"]),
            Field("account", "What do you actually say or do?", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
