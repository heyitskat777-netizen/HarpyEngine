"""One optional physical interception decision for each actual Sprite controller."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_sprite import SpriteService


async def open_sprite(
    interaction: discord.Interaction, service: SpriteService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if data["state"] != "pending" or data["phase"] != "choose" or data["answered"]:
        await reply(
            interaction,
            ("Your interception decision is saved; the remaining consequences are being resolved."),
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        selected = values["option"][0]
        option = data["options"][int(selected)] if selected != "pass" else None
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            data["game_revision"],
            ActorRef.model_validate(option["actor"]) if option else None,
            option["asset"] if option else None,
            values["account"],
        )
        return "Your Sprite's decision is saved. The original roll is preserved."

    form = NativeForm(
        interaction.user.id,
        "Sprite: leap in to take the blow",
        (
            "Choose one of your actual nearby Sprites or decline. "
            "Interception damages its selected Asset and protects the original body."
        ),
        [
            Field(
                "option",
                "Your interception",
                (("pass", "Decline interception"),)
                + tuple((str(i), x["label"]) for i, x in enumerate(data["options"])),
            ),
            Field("account", "Describe your Sprite's actual response", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
