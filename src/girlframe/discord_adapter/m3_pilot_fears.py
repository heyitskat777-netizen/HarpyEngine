"""Private owned controls for the Directors' demand and Cadre's actual response."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_pilot_fears import FearsService


async def open_fears(
    interaction: discord.Interaction,
    service: FearsService,
    identity: str,
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    options = []
    if data["issue"]:
        options.append(("demand", "Make the actual demand"))
    if data["respond"]:
        options.append(("respond", "Record my Girl's actual response in this scene"))
    if data["review"]:
        if data["responses"]:
            options.append(("addressed", "Accept a recorded Cadre response"))
        options.append(("discipline", "Call for collective Severe Punishment"))
    prompt = data["demand"] or "Speak the original Directors' demand to the Cadre."
    if not options:
        result = {
            "addressed": "The Directors accepted the response.",
            "discipline": "The Directors called for collective Severe Punishment.",
        }
        await reply(interaction, prompt + "\n" + result.get(data["result"], "Awaiting a response."))
        return
    fields = [
        Field("action", "Your action in the original demand", tuple(options)),
        Field("account", "What actually happens?", paragraph=True),
    ]
    if data["review"] and data["responses"]:
        fields.append(
            Field(
                "response",
                "Which recorded action satisfies the demand?",
                data["responses"],
                required=False,
            )
        )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        action = values["action"][0]
        response = values.get("response", ())
        result = await asyncio.to_thread(
            service.act,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            action,
            values["account"],
            channel=current.channel_id if action == "respond" else None,
            evidence=response[0] if response else None,
        )
        if result["state"] == "discipline":
            return "Collective Severe Punishment is required. The actual cases are in the Inbox."
        return "The original demand record was updated."

    await NativeForm(
        interaction.user.id,
        "Directors' public-fear demand",
        prompt,
        fields,
        submit,
    ).present(interaction)
