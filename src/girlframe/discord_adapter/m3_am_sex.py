"""Private AM counterpart-Play and real circuit-maintenance navigation."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_am_sex import SexService
from girlframe.services.onboarding import WorkflowError


async def open_am_sex(interaction: discord.Interaction, service: SexService) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.menu, viewer, int(interaction.channel_id or 0))
    options = [("circuits", "Actual circuit contact: use Just Code")]
    options += [
        (x["id"], x["play"].replace("_", " ") + " · " + x["state"]) for x in data["sources"]
    ]

    async def select(current: discord.Interaction, values: dict[str, Any]) -> None:
        source = values["source"][0]
        if source == "circuits":
            from girlframe.discord_adapter.m3_am_code import open_code
            from girlframe.services.m3_am_code import CodeService

            await open_code(current, CodeService(service.game))
            return
        fresh = await asyncio.to_thread(
            service.menu, viewer_from_interaction(current), data["channel"]
        )
        actual = next((x for x in fresh["sources"] if x["id"] == source), None)
        if actual is None:
            raise WorkflowError("Reopen the actual original counterpart source")
        if actual["choices"]:
            from girlframe.discord_adapter.m2_ui import open_choice

            await open_choice(current, service.game, actual["choices"][0])
        else:
            await reply(
                current,
                "Counterpart source `"
                + actual["id"]
                + "` · "
                + actual["state"]
                + (
                    " · receipt `" + actual["receipt"] + "`"
                    if actual["receipt"]
                    else " · awaiting its actual roll"
                )
                + ". AM makes no additional Sex roll. Original source owners retain their choices.",
            )

    form = NativeForm(
        viewer.user_id,
        "AM: counterpart source",
        (
            "Your counterpart uses their own genuine Sex Play after its actual "
            "voluntary source confirmation. "
            "AM makes no additional Sex roll, marks no extra Identity "
            "and spends no extra Heat here. "
            "If someone actually accesses your circuits, use the existing Just Code controls "
            "and its separate source confirmation. "
            "This card does not grant circuit access or make a choice for either player."
        ),
        [Field("source", "Open actual source", tuple(options))],
        select,
    )
    await reply(interaction, form.text(), form)
