"""The actual Handler's source-owned replacement for Asset damage or Helplessness."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_handler_consequences import HandlerConsequenceService
from girlframe.services.onboarding import WorkflowError


async def open_consequence(
    interaction: discord.Interaction, service: HandlerConsequenceService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if not data["can_act"]:
        await reply(
            interaction, "This original Handler consequence is already resolved or its body ended."
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        choice = values["choice"][0]
        if choice == "death" and values.get("confirmation", "") != "END THIS HANDLER":
            raise WorkflowError(
                "Type END THIS HANDLER only if you choose this actual body's death."
            )
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["game_revision"],
            choice,
            values["account"],
        )
        return (
            "Original Handler body archived. Your human GM role continues; create a fresh persona "
            "with fresh owned choices."
            if choice == "death"
            else "Actual consequence recorded. The offered opening or persistent injury is saved."
        )

    form = NativeForm(
        viewer.user_id,
        "Handler consequence",
        "This actual source would damage an Asset or cause Helplessness. Choose its printed "
        "replacement and describe the real effect for the scene. Death ends this original body.",
        [
            Field(
                "choice",
                "Your actual replacement consequence",
                (
                    ("opportunity", "Offer an opportunity"),
                    ("chance_to_act", "Offer a chance to act"),
                    ("weakness", "Offer a moment of weakness"),
                    ("injury", "Suffer an injury and survive"),
                    ("death", "This Handler dies"),
                ),
            ),
            Field("account", "Actual opening, persistent injury or death", paragraph=True),
            Field("confirmation", "For death only: END THIS HANDLER", required=False),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
