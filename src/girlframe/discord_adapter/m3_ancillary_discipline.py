"""Native controls for an old source discipline action and confidence spend."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_ancillary_discipline import AncillaryDisciplineService
from girlframe.services.m3_prodigy_swoon import SwoonService


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
    channel: int,
) -> None:
    viewer = viewer_from_interaction(interaction)
    swoon = SwoonService(service.game)
    data = await asyncio.to_thread(swoon.menu, viewer, channel, actor)
    choices: tuple[tuple[str, str], ...] = (("status", "Improve Status"),) if data["owned"] else ()
    choices += tuple((key, "Make " + label + " swoon") for key, label in data["npcs"].items())
    if not choices:
        await reply(interaction, "There is no current confidence spend available here.")
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        selected = values["choice"][0]
        if selected == "status":
            await asyncio.to_thread(
                service.spend,
                viewer_from_interaction(click),
                str(click.id),
                actor,
                data["owned"][0],
                data["revision"],
            )
            return "Your original Status improved."
        await asyncio.to_thread(
            swoon.offer,
            viewer_from_interaction(click),
            str(click.id),
            channel,
            actor,
            data["revision"],
            data["notches"][0],
            selected,
        )
        return "The original NPC controller has a private response."

    form = NativeForm(
        interaction.user.id,
        "Earned Confidence",
        "Spend one of your original unspent notches.",
        [Field("choice", "Your decision", choices)],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_swoon(
    interaction: discord.Interaction, service: SwoonService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    owner = data["role"] == "withdraw"
    choices = (
        (("withdraw", "Withdraw the request"),)
        if owner
        else (
            ("confirm", "Record the original NPC's reaction"),
            ("decline", "Decline"),
        )
    )
    fields = [Field("choice", "Your decision", choices)]
    if not owner:
        fields.append(Field("account", "Your own NPC’s reaction", paragraph=True, required=False))

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.answer,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            values["choice"][0],
            values.get("account", ""),
        )
        return "The original decision is saved."

    subject = clean(data["known"]) if data["known"] else "the original Prodigy"
    form = NativeForm(
        viewer.user_id,
        "Earned Confidence",
        "Release your original reserved notch."
        if owner
        else "Choose your NPC’s reaction to " + subject + ".",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)
