"""Native actual source-group merger; no automatic NPC dialogue or movement."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_rebel_merge import MergerService


async def open_merger(
    interaction: discord.Interaction, service: MergerService, identity: str
) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    if data["state"] != "pending":
        await reply(interaction, "This Rebel Group merger is already saved.")
        return
    if not data["receiving"]:
        await reply(
            interaction, "Introduce another actual active Rebel Group, then reopen the merger."
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.apply,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            data["game_revision"],
            values["receiving"][0],
            values["account"],
        )
        return "The actual merger and its membership/territory changes are saved."

    form = NativeForm(
        interaction.user.id,
        "Rebel Group funding and merger",
        "Choose the existing receiving group. People and their physical positions remain; "
        "group memberships and territory follow the actual merger.",
        [
            Field(
                "receiving",
                "Receiving active Rebel Group",
                tuple((x["id"], x["label"]) for x in data["receiving"]),
            ),
            Field("account", "Actual funding loss and merger", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
