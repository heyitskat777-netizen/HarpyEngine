"""The original human GM reviews and designates Foundation standing."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_expanded_status import LEVELS
from girlframe.services.m3_expanded_status import ExpandedStatusService


async def open_status(interaction: discord.Interaction, service: ExpandedStatusService) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.options, viewer)
    targets = {actor.token: actor for actor, _, _ in data["actors"]}
    if not targets:
        await reply(interaction, "There are no current actors within Foundation Status.")
        return

    async def designate(current: discord.Interaction, values: dict[str, Any]) -> str:
        level = next(level for level in LEVELS if str(level) == values["level"][0])
        await asyncio.to_thread(
            service.designate,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            targets[values["actor"][0]],
            level,
            values["account"],
        )
        return "The original actor's Foundation standing is saved."

    await NativeForm(
        viewer.user_id,
        "Expanded Status",
        "Designate standing for an actual actor. Order authority is adjudicated separately.",
        [
            Field(
                "actor",
                "Actual actor",
                tuple(
                    (actor.token, f"{name} · {LEVELS[level]}")
                    for actor, name, level in data["actors"]
                ),
            ),
            Field(
                "level",
                "Foundation standing",
                tuple((str(key), label) for key, label in LEVELS.items()),
            ),
            Field("account", "Factual basis", paragraph=True),
        ],
        designate,
    ).present(interaction)
