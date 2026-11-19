"""Private owned controls for the Directors' demand and Cadre's actual response."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_strain_state import TRACKS
from girlframe.services.m3_pilot_fears import FearsService


async def open_fears(
    interaction: discord.Interaction,
    service: FearsService,
    identity: str,
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    appearance = data["city"] is not None
    title = "Cadre public appearance" if appearance else "Directors' public-fear demand"
    severity = "Moderate" if appearance else "Severe"
    options = []
    if data["issue"]:
        options.append(("demand", "Make the actual demand"))
    if data["respond"]:
        options.append(
            (
                "respond",
                "Record my Girl's attendance"
                if appearance
                else "Record my Girl's actual response in this scene",
            )
        )
    if data["review"]:
        if data["responses"]:
            options.append(("addressed", "Accept a recorded Cadre response"))
        if not appearance or data["responses"]:
            options.append(("discipline", "Call for collective " + severity + " Punishment"))
    prompt = data["demand"] or "Speak the original Directors' demand to the Cadre."
    if not options:
        result = {
            "addressed": "The public appearance was accepted."
            if appearance
            else "The Directors accepted the response.",
            "discipline": "Collective " + severity + " Punishment was required.",
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
                "Choose a response from the actual appearance"
                if appearance
                else "Which recorded action satisfies the demand?",
                data["responses"],
                required=False,
            )
        )
    if appearance and data["review"]:
        fields.append(
            Field(
                "track",
                "Which Strain rises if the appearance failed?",
                tuple((x, x.title()) for x in TRACKS),
                required=False,
            )
        )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        action = values["action"][0]
        response = values.get("response", ())
        track = values.get("track", ())
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
            track=track[0] if action == "discipline" and track else None,
        )
        if result["state"] == "discipline":
            return "Collective " + severity + " Punishment is required. The cases are in the Inbox."
        return "The original demand record was updated."

    await NativeForm(
        interaction.user.id,
        title,
        prompt,
        fields,
        submit,
    ).present(interaction)
