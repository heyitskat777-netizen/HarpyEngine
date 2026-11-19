"""Private native controls for the original and willing successor."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_budget_demotion import DemotionService


async def open_demotion(
    interaction: discord.Interaction, service: DemotionService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    phase = data["phase"]
    if phase == "nomination":
        if not data["nominees"]:
            await reply(interaction, "A different joined player can accept the new Handler role.")
            return

        async def nominate(click: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.respond,
                viewer_from_interaction(click),
                str(click.id),
                identity,
                data["revision"],
                "nominate",
                nominee=int(values["nominee"][0]),
                account=values["account"],
            )
            return "The invited player can answer from their private Inbox."

        await NativeForm(
            interaction.user.id,
            "Nominate a successor",
            "The nominated player chooses whether to take office.",
            [
                Field("nominee", "Joined player", data["nominees"]),
                Field("account", "Your offer", paragraph=True),
            ],
            nominate,
        ).present(interaction)
        return

    status = {
        "offer": "The original Handler has offered succession.",
        "declined": "The invited player declined.",
        "demotion_due": "The original Handler will leave office at the close of Off-Duty.",
        "girl_creation": "The former Handler can finish their own Girl creation now.",
        "appointment": "The original Girl is active. The consenting successor awaits appointment.",
        "handler_creation": "The appointed successor can activate their own Handler persona.",
        "complete": "Both original roles are now active.",
    }[phase]
    text = "\n\n".join(x for x in (status, clean(data["account"])) if x)
    if not data["options"]:
        await reply(interaction, text[:1800])
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            values["choice"][0],
        )
        return "Your owned succession decision has been recorded."

    await NativeForm(
        interaction.user.id,
        "Budget Endgame demotion",
        text[:1600],
        [Field("choice", "Your decision", data["options"])],
        submit,
    ).present(interaction)
