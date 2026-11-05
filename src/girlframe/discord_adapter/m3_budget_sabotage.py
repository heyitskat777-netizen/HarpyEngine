"""Original Handler describes only actual revealed Asset failures."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.services.m2_game import GameService


async def open_calamity(interaction: discord.Interaction, game: GameService, identity: str) -> None:
    data = await asyncio.to_thread(game.decision, viewer_from_interaction(interaction), identity)

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            ChoiceAnswer(fields=values),
        )
        return "The revealed failures are saved; other effects and original costs are preserved."

    form = NativeForm(
        interaction.user.id,
        "Revealed Asset failure",
        "Describe how each attempted Asset failed. Its maneuvers fail; "
        "other maneuvers and the original Play's costs still apply.",
        [
            Field(x["id"], "Failure: " + x["label"], paragraph=True)
            for x in data["asset_calamities"]
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
