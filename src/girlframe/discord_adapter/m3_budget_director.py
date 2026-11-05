"""Two actual humans conduct the required Director performance meeting."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_budget_director import MeetingService


async def open_meeting(
    interaction: discord.Interaction, service: MeetingService, identity: str
) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    fields = []
    if data["phase"] == "appearance" and not data["handler"]:
        action = "appear"
        fields = [
            Field(
                "appearance",
                "Your actual Director",
                (("appear", "I actually appear for this meeting"),),
            )
        ]
    elif data["phase"] == "setup" and data["handler"]:
        action = "start"
        if not data["overlapping"]:
            fields = [
                Field("first", "First ordinary Identity"),
                Field("second", "Second ordinary Identity"),
            ]
    elif data["phase"] == "active" and not data["handler"]:
        action = "end"
        fields = [
            Field(
                "departure",
                "Actual ending",
                (("end", "The meeting ended and I left their presence"),),
            )
        ]
    else:
        await reply(
            interaction,
            "The meeting is " + data["phase"] + ". Waiting for the other original participant.",
        )
        return
    fields.append(Field("account", "Describe your actual appearance or meeting", paragraph=True))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        labels = (values["first"], values["second"]) if "first" in values else ()
        await asyncio.to_thread(
            service.act,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            action,
            values["account"],
            labels,
        )
        return "Your actual meeting response is saved."

    form = NativeForm(
        interaction.user.id,
        "Director: performance meeting",
        "A different human plays the Director. The Handler uses Girl rules in their presence. "
        "This event grants 4 Heat once.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)
