"""Native genuine award purchase and saved original insurance history."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_girl_insurance import GirlInsuranceService


async def open_insurance(
    interaction: discord.Interaction, service: GirlInsuranceService, identity: str | None = None
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), identity)
    if data["historical"] or data["owned"]:
        records = []
        for record in data["records"]:
            records.append(
                "Held for the next actual Girl death."
                if record["phase"] == "held"
                else "Consumed by an actual original Girl death: Budget "
                + record["budget_before"]
                + " → "
                + record["budget_after"]
                + "."
            )
        await reply(interaction, "**Girl Insurance**\n" + "\n".join(records))
        return
    if not data["awards"]:
        await reply(interaction, "Girl Insurance costs one actual held Handler advancement.")
        return

    async def buy(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.buy,
            viewer_from_interaction(current),
            str(current.id),
            values["award"][0],
            data["revision"],
            values["account"],
        )
        return "Girl Insurance acquired. One actual advancement spent; no Permissions charged."

    await NativeForm(
        interaction.user.id,
        "Acquire Girl Insurance",
        "The next actual Girl death does not raise Budget Strain. High Budget becomes Low, "
        "then this advancement is lost. Actual death consumes it automatically; "
        "a proposal or a prevented death does not.",
        [
            Field(
                "award",
                "Actual held advancement",
                tuple(
                    (x["id"], x["rule"].replace("strain.void.endgame.", "Void Endgame "))
                    for x in data["awards"]
                ),
            ),
            Field("account", "Record this actual acquisition", paragraph=True),
        ],
        buy,
    ).present(interaction)
