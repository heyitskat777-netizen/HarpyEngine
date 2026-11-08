"""Private original-person controls for actual Wyvern restraints and replacement Plays."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m2_game import GameService
from girlframe.services.m3_wyvern_combat import WyvernCombatService
from girlframe.services.onboarding import WorkflowError


async def open_combat(interaction: discord.Interaction, game: GameService, identity: str) -> None:
    service = WyvernCombatService(game)
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    options = []
    if data.get("can_resume"):
        options.append(("resume", "Resume your actual existing Play"))
    if data["can_counter"]:
        options.append(("counter", "Make the actual required Play"))
    if data["can_release"]:
        options.append(("release", "Actually release this person"))
    text = "**" + discord.utils.escape_markdown(data["label"]) + "**\n" + data["summary"]
    if not options:
        await reply(interaction, text)
        return

    async def choose(current: discord.Interaction, operation: str) -> None:
        latest = await asyncio.to_thread(service.view, viewer_from_interaction(current), identity)
        if operation == "resume" and latest.get("can_resume"):
            from girlframe.discord_adapter.m2_ui import open_pending

            await open_pending(current, game)
            return
        if operation == "counter" and latest["can_counter"]:
            from girlframe.discord_adapter.m2_ui import open_play

            await open_play(current, game, parent=latest["counter"])
            return
        if operation != "release" or not latest["can_release"]:
            raise WorkflowError("Reopen the actual current source and its original choices")

        async def release(actual: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.release_pin,
                viewer_from_interaction(actual),
                str(actual.id),
                identity,
                latest["revision"],
                values["account"],
            )
            return "Your actual release is saved."

        await NativeForm(
            current.user.id,
            "Release the actual pinned person",
            "Describe your performed release of this original person.",
            [Field("account", "Your actual release", paragraph=True)],
            release,
        ).present(current)

    await Picker(interaction.user.id, text, tuple(options), choose).show(interaction)
