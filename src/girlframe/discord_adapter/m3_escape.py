"""Native private controls for the original Escape roll and its outcomes."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_escape import EscapeService


async def open_escape(
    interaction: discord.Interaction, service: EscapeService, channel: int, actor: ActorRef
) -> None:
    data = await asyncio.to_thread(
        service.menu, viewer_from_interaction(interaction), channel, actor
    )

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        heat = values["heat"].strip()
        if not heat.isascii() or not heat.isdecimal() or len(heat) > 9:
            raise ValueError("Enter the actual amount of Heat")
        await asyncio.to_thread(
            service.start,
            viewer_from_interaction(click),
            str(click.id),
            channel,
            actor,
            data["revision"],
            int(heat),
            values["account"],
        )
        return "The original roll is saved. Open the private Inbox."

    fields = [
        Field("heat", "Actual Heat to spend"),
        Field("account", "Record the scene in broad terms", paragraph=True),
    ]
    form = NativeForm(
        interaction.user.id,
        "Escape",
        f"Confirm your original scene. You have {data['heat']} Heat.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_escape_choice(
    interaction: discord.Interaction, service: EscapeService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    step = data["step"]
    if step == "erase":
        text = "Choose one of your actual eligible Identities to erase."
        options = data["identities"]
        fields = (
            [Field("choice", "Your original Identity", tuple(options.items()))] if options else []
        )
    elif step in ("find", "ward"):
        text = "Record the actual finder or base personnel from the original scene."
        options = data["people"]
        fields = (
            [
                Field("choice", "Actual present person", tuple(options.items())),
                Field("account", "Record the actual outcome", paragraph=True),
            ]
            if options
            else []
        )
    elif step == "rescue":
        text = (
            clean(data["account"])
            + "\nThe original finder can save her. Other outcomes await the human GM."
        )
        fields = [
            Field("choice", "Your decision", (("save", "Save the original Girl"),)),
            Field("account", "Record the rescue in broad terms", paragraph=True),
            Field("tag", "Optional Tag that also makes her the Dog", required=False),
        ]
    else:
        text = "Verify the original sickbay restraint has actually ended."
        fields = [
            Field("choice", "Actual decision", (("release", "Confirm the release"),)),
            Field("account", "Record the actual release", paragraph=True),
        ]
    if not fields:
        await reply(interaction, "The original outcome awaits an eligible actual source.")
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.act,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            step,
            choice=values["choice"][0],
            account=values.get("account", ""),
            tag=values.get("tag", ""),
        )
        return "The original Escape consequence is saved."

    form = NativeForm(interaction.user.id, "Escape", text, fields, submit)
    await reply(interaction, form.text(), form)
