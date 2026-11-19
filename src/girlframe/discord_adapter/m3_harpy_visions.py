"""Native private choices for a Harpy’s actual Visions of Infinity."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_harpy_visions import VisionsService

TITLE = "Visions of Infinity"


async def open_visions(
    interaction: discord.Interaction,
    service: VisionsService,
    channel: int,
    actor: ActorRef,
) -> None:
    data = await asyncio.to_thread(
        service.targets, viewer_from_interaction(interaction), channel, actor
    )
    if not data["targets"]:
        await reply(interaction, "No eligible original recipient is present for this Play.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.start,
            viewer_from_interaction(current),
            str(current.id),
            channel,
            actor,
            data["revision"],
            values["target"][0],
            values["account"],
        )
        return "The original recipient’s consent is pending."

    fields = [
        Field("target", "Original recipient", tuple(data["targets"].items())),
        Field("account", "Describe how your Harpy approaches", paragraph=True),
    ]
    form = NativeForm(interaction.user.id, TITLE, "Choose an actual present Girl.", fields, submit)
    await reply(interaction, form.text(), form)


async def open_visions_response(
    interaction: discord.Interaction,
    service: VisionsService,
    identity: str,
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    step = data["step"]
    if step == "consent":
        text = data["account"]
        fields = [
            Field("choice", "Your decision", (("yes", "Allow the contact"), ("no", "Decline"))),
        ]
    elif step == "roll":
        text = f"The original Girl allowed the contact. Your Harpy has {data['heat']} Heat."
        fields = [Field("heat", "Your actual Heat spend")]
    elif step == "replace" and data["can_replace"]:
        text = "Confirm the original low result. Your new Identities would be " + ", ".join(
            data["identities"]
        )
        fields = [Field("choice", "Actual original effect", (("yes", "Apply this change"),))]
    else:
        await reply(interaction, "The original saved outcome awaits its actual consequence.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        heat = values.get("heat", "").strip()
        if step == "roll" and (not heat.isascii() or not heat.isdecimal() or len(heat) > 9):
            return "Enter a whole amount of your available Heat."
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            step,
            heat=int(heat) if step == "roll" else None,
            choice=values["choice"][0] == "yes" if "choice" in values else None,
        )
        return "The original private decision is saved."

    form = NativeForm(interaction.user.id, TITLE, text, fields, submit)
    await reply(interaction, form.text(), form)
