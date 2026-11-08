"""Actual fight participation and an ending backed by existing combat receipts."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_budget_fight import FightService


async def open_fight(
    interaction: discord.Interaction, service: FightService, identity: str
) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    context = " and ".join(data["people"]) + ": televised fight in <#" + str(data["channel"]) + ">."
    if data["phase"] == "complete":
        await reply(interaction, context + " The actual fight has ended.")
        return
    if data["handler"]:
        if data["phase"] != "fighting" or not data["completed"]:
            await reply(
                interaction,
                context + " Confirm participation, then use /play battle in that scene. "
                "then reopen this request after its real consequences finish.",
            )
            return
        action = "end"
        fields = [
            Field(
                "confirm", "Actual fight ending", (("yes", "The actual televised fight has ended"),)
            ),
            Field("account", "Describe the actual ending", paragraph=True),
        ]
    elif not data["attended"]:
        action = "attend"
        fields = [
            Field(
                "confirm",
                "My participation",
                (("yes", "I actually participate in this televised fight"),),
            ),
            Field("account", "Describe your actual participation", paragraph=True),
        ]
    else:
        await reply(
            interaction,
            context
            + " Your participation is saved. Continue the fight using /play battle in that scene; "
            "combat choices remain yours.",
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.act,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            action,
            values["account"],
        )
        return "Your fight response is saved."

    form = NativeForm(interaction.user.id, "Televised fight", context, fields, submit)
    await reply(interaction, form.text(), form)
