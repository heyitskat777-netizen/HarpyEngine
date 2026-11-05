"""Actual original-human memorial, with no new living character or invented response."""

import asyncio
from typing import Any, Literal, cast

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_martyr as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_martyr import MartyrService
from girlframe.services.onboarding import WorkflowError


async def open_purchase(interaction: discord.Interaction, service: MartyrService) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction))
    if not data["available"]:
        raise WorkflowError(
            "This native Martyr acquisition needs reviewed Class rules and existing Strain"
        )
    if data["owned"]:
        await reply(interaction, "Martyr is acquired for your current actual Autocrat Frame.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.buy,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            ActorRef.model_validate(data["actor"]),
            data["frame"],
            values["account"],
        )
        return (
            "Martyr acquired for two Permissions. Your memorial choice appears after actual death."
        )

    await NativeForm(
        interaction.user.id,
        "Martyr — native Autocrat, 2 Permissions",
        "An actual unprevented original death lowers Budget and Rebellion to Low. "
        "Then you choose its memorial.",
        [Field("account", "Record your actual acquisition", paragraph=True)],
        submit,
    ).present(interaction)


async def open_memorial(
    interaction: discord.Interaction, service: MartyrService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if not data["can_act"]:
        await reply(
            interaction,
            "Your original character's memorial: "
            + str(data["episode"]["memorial"])
            + "\n"
            + (data["episode"]["response_account"] or ""),
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.choose,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            cast(Literal["hero", "obscurity"], values["memorial"][0]),
            values["account"],
        )
        return "The memorial for " + str(data["callsign"]) + " is saved."

    await NativeForm(
        interaction.user.id,
        "Remember " + str(data["callsign"]),
        "You own this authorial choice as the original character's human.",
        [
            Field("memorial", "How are they remembered?", rules.MEMORIALS),
            Field("account", "Describe their actual memorial or obscurity", paragraph=True),
        ],
        submit,
    ).present(interaction)
