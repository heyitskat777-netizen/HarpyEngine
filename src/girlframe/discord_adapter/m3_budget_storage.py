"""Native original-owner storage, higher-up warnings and source-proved endings."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field
from girlframe.discord_adapter.m3_strain_effects import DependentForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_budget_storage import StorageService


async def open_storage(
    interaction: discord.Interaction, service: StorageService, identity: str
) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    if not data["actions"]:
        await reply(
            interaction,
            data["blocked"]
            or "No response is due from you. This original storage order remains saved.",
        )
        return

    def build(values: dict[str, Any]) -> list[Field]:
        action = values.get("action", (data["actions"][0][0],))[0]
        fields = [Field("action", "Your actual owned response", tuple(data["actions"]))]
        if action == "warn":
            fields.append(Field("label", "Warning Tag given by this actual higher-up"))
        fields.append(
            Field("account", "Your actual storage, refusal, warning or ending", paragraph=True)
        )
        return fields

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.act,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["action"][0],
            values["account"],
            label=values.get("label", ""),
        )
        return "Your actual storage-order response is saved."

    form = DependentForm(
        interaction.user.id,
        "Frame storage: " + data["owner"][:60],
        "Order: store this original Frame empty at " + data["base"] + ". "
        "Use actual cockpit and movement controls first. "
        "Warning and firing require distinct actual breaches; "
        "release requires a real later Budget reduction. " + data["blocked"],
        build,
        submit,
    )
    await reply(interaction, form.text(), form)
