"""Original-controller flesh-layer descriptions without another resource pool."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_leviathan import LeviathanService


async def open_layers(
    interaction: discord.Interaction, service: LeviathanService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.protect,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            data["source_sha256"],
            (values["layer_one"], values["layer_two"]),
            values["account"],
        )
        return "Two actual flesh-layer Assets protect this original Core. Their damage is saved."

    form = NativeForm(
        interaction.user.id,
        "Leviathan: protect your Core",
        "Describe two real flesh layers. Both must be pierced before new Core exposure; "
        "the original Core guards and weakness still apply.",
        [
            Field("layer_one", "First flesh layer", paragraph=True),
            Field("layer_two", "Second flesh layer", paragraph=True),
            Field("account", "Actual protective action", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
