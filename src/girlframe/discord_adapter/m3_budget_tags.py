"""Owned persistent Endgame Tag gift; the actual Girl supplies its wording."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_budget_tags import BudgetTagService


async def open_gift(
    interaction: discord.Interaction, service: BudgetTagService, identity: str
) -> None:
    view = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    if not view["original_alive"] or not view["girl_alive"]:

        async def close(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.close_original,
                viewer_from_interaction(current),
                str(current.id),
                view["id"],
                view["game_revision"],
            )
            return "The request's actual original ending is recorded."

        form = NativeForm(
            interaction.user.id,
            "Original Endgame participant ended",
            "Review the proved original ending before closing this pending request.",
            [Field("confirm", "Review actual source", (("close", "Record this original ending"),))],
            close,
        )
        await reply(interaction, form.text(), form)
        return
    if view["gift"] is not None:
        if view["gift"]["stage"] != "awaiting_girl" or interaction.user.id != int(
            view["gift"]["girl"]["entity"]
        ):
            await reply(
                interaction,
                "The original selected Girl names this Handler Tag in her private requests.",
            )
            return

        async def give(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.give,
                viewer_from_interaction(current),
                str(current.id),
                view["id"],
                view["game_revision"],
                values["tag"],
                values["account"],
            )
            return (
                "Your actual Handler Tag is saved. It remains when used for a Handler Tag effect."
            )

        form = NativeForm(
            interaction.user.id,
            "Your persistent Handler Tag",
            "Give the original Handler a Tag in your own words.",
            [
                Field("tag", "The Tag"),
                Field("account", "Describe why you give this Tag", paragraph=True),
            ],
            give,
        )
    else:

        async def nominate(current: discord.Interaction, values: dict[str, Any]) -> str:
            selected = next(
                x
                for x in view["girls"]
                if ActorRef.model_validate(x["ref"]).token == values["girl"][0]
            )
            await asyncio.to_thread(
                service.nominate,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                view["revision"],
                view["game_revision"],
                ActorRef.model_validate(selected["ref"]),
                values["account"],
            )
            return "The actual selected Girl can name her Tag in /character requests."

        form = NativeForm(
            interaction.user.id,
            "Persistent Handler Tag Endgame",
            "Select the actual Girl; she supplies her own Tag wording.",
            [
                Field(
                    "girl",
                    "Actual Girl",
                    tuple(
                        (ActorRef.model_validate(x["ref"]).token, x["name"]) for x in view["girls"]
                    ),
                ),
                Field("account", "Describe the actual event", paragraph=True),
            ],
            nominate,
        )
    await reply(interaction, form.text(), form)
