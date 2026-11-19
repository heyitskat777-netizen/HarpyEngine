"""Native controls for an old source discipline action and confidence spend."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_ancillary_discipline import AncillaryDisciplineService


async def open_cadre_punishment(
    interaction: discord.Interaction,
    service: AncillaryDisciplineService,
    channel: int,
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), channel)
    if not data["people"]:
        await reply(interaction, "There is no current eligible member to choose.")
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.start,
            viewer_from_interaction(click),
            str(click.id),
            channel,
            data["revision"],
            values["person"][0],
        )
        return "The original case is in its private discipline Inbox."

    form = NativeForm(
        interaction.user.id,
        "Ancillary Cadre discipline",
        "Use your actual Handler authority to open an owned Punishment scene.",
        [Field("person", "Actual original Cadre member", tuple(data["people"].items()))],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_confidence(
    interaction: discord.Interaction,
    service: AncillaryDisciplineService,
    actor: ActorRef,
) -> None:
    data = await asyncio.to_thread(
        service.confidence_menu, viewer_from_interaction(interaction), actor
    )
    if not data["owned"]:
        await reply(interaction, "You have no unspent notch that can improve your Status.")
        return

    async def submit(click: discord.Interaction, _values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.spend,
            viewer_from_interaction(click),
            str(click.id),
            actor,
            data["owned"][0],
            data["revision"],
        )
        return "Your original Status improved."

    form = NativeForm(
        interaction.user.id,
        "Earned Confidence",
        f"You have {len(data['owned'])} unspent notches. Spend one to improve your actual Status.",
        [Field("choice", "Your decision", (("yes", "Spend one notch"),))],
        submit,
    )
    await reply(interaction, form.text(), form)
