"""Private rule review; only the informed Handler records actual breaches."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_regulations import RegulationService


async def open_regulations(interaction: discord.Interaction, service: RegulationService) -> None:
    viewer = viewer_from_interaction(interaction)
    rules = await asyncio.to_thread(service.list, viewer)
    if not rules:
        await reply(interaction, "No behavioural rule is available to your actual role.")
        return

    async def choose(current: discord.Interaction, identity: str) -> None:
        data = await asyncio.to_thread(service.get, viewer_from_interaction(current), identity)
        text = "**Behavioural rule**\n" + clean(data["rule"])
        text += "\n" + (
            "The affected Girl was informed."
            if data["disclosed"]
            else "Concealed from the affected Girl."
        )
        if not data["may_record"]:
            await reply(current, text)
            return

        async def submit(actor: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.record,
                viewer_from_interaction(actor),
                str(actor.id),
                identity,
                data["game_revision"],
                values["evidence"],
                values["due"][0],
            )
            return "The observed breach and its separate discipline cause are saved."

        form = NativeForm(
            viewer.user_id,
            "Record observed breach",
            text + "\nConfirm an actual occurrence and when its Punishment is due. "
            "The bot does not monitor chat or decide whether a rule was broken.",
            [
                Field("evidence", "Describe the observed occurrence", paragraph=True),
                Field("due", "When is Punishment due?", tuple(data["due_options"])),
            ],
            submit,
        )
        await reply(current, form.text(), form)

    await Picker(
        viewer.user_id,
        "**Behavioural rules known to your role**",
        tuple((x["id"], x["label"]) for x in rules),
        choose,
    ).show(interaction)
