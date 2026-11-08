"""A patron's actual human reports visits and their observed evidence."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_budget_patron import PatronService


async def open_patron(
    interaction: discord.Interaction, service: PatronService, identity: str
) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.visit,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["witnessed"][0] == "yes",
            values["account"],
            values.get("tag", ""),
        )
        return "Visit saved." + (
            " The actual patron's Handler Tag is saved." if result["tag"] else ""
        )

    form = NativeForm(
        interaction.user.id,
        "Patron visit: " + data["patron"],
        "Report an actual visit to "
        + data["girl"]
        + ". Private records do not establish what this person saw.",
        [
            Field(
                "witnessed",
                "Did the patron actually see evidence?",
                (("no", "No evidence seen"), ("yes", "Saw evidence of Punishment")),
            ),
            Field("tag", "If evidence was seen: Handler Tag", required=False),
            Field("account", "Describe the actual visit and observation", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
