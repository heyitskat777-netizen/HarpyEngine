"""Explicit human Handler totals, clearly labelled as manual decisions without dice."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_adjudication import AdjudicationService
from girlframe.services.onboarding import WorkflowError


async def open_adjudication(
    interaction: discord.Interaction, service: AdjudicationService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if not data["can_act"]:
        await reply(interaction, "This mandatory Play awaits its actual Handler's manual decision.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        try:
            total = int(values["total"])
        except (ValueError, TypeError):
            raise WorkflowError("Enter the actual integer total assigned before Tags.") from None
        await asyncio.to_thread(
            service.submit,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            total,
            values["reason"],
        )
        return (
            "Manual adjudication recorded without dice or Heat spending. Actual Tag choices follow."
        )

    form = NativeForm(
        viewer.user_id,
        "Manual adjudication — " + clean(data["patient"]),
        "The original Girl cannot roll this mandatory Play after surgery. Assign the whole "
        "pre-Tag total and describe your ruling. No RNG, dice faces or automatic favorable "
        "result is generated. Play: " + data["play"].replace("_", " "),
        [
            Field("total", "Assigned total before Tags"),
            Field("reason", "Actual no-roll ruling and circumstances", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
