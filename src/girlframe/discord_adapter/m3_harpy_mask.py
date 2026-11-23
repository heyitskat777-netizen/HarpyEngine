"""Native controls for a scene-scoped Human Mask."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_harpy_mask import MaskService

TITLE = "A Human Mask"


async def open_mask(
    interaction: discord.Interaction, service: MaskService, channel: int, actor: ActorRef
) -> None:
    data = await asyncio.to_thread(
        service.get, viewer_from_interaction(interaction), channel=channel
    )

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.offer,
            viewer_from_interaction(click),
            str(click.id),
            channel,
            actor,
            data["revision"],
            values["appearance"],
            values["account"],
        )
        return "The original human facilitator can review your appearance."

    fields = [
        Field("appearance", "Human appearance"),
        Field("account", "Describe the actual infiltration", paragraph=True),
    ]
    form = NativeForm(
        interaction.user.id,
        TITLE,
        "Describe how your Harpy presents in this scene.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_mask_response(
    interaction: discord.Interaction, service: MaskService, identity: str
) -> None:
    data = await asyncio.to_thread(
        service.get, viewer_from_interaction(interaction), identity=identity
    )
    step = data["step"]
    choices = (
        (("yes", "Approve this appearance"), ("no", "Decline"))
        if step == "review"
        else (("yes", "End this appearance"),)
    )

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            step,
            values["allow"][0] == "yes",
            values["account"],
        )
        return "The original Human Mask decision is saved."

    text = clean(data["appearance"])
    if step == "review":
        text += "\n" + clean(data["account"])
    form = NativeForm(
        interaction.user.id,
        TITLE,
        text,
        [
            Field("allow", "Actual decision", choices),
            Field("account", "Describe the result", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
