"""Explicit notice, actual attendance and player-authored conditional Tags."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_political_function import FunctionService


async def open_function(
    interaction: discord.Interaction, service: FunctionService, identity: str
) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    if data["phase"] == "complete":
        await reply(
            interaction, "This function has ended; its conditional Tag permission has expired."
        )
        return
    if data["handler"]:
        if data["phase"] != "active":
            await reply(
                interaction,
                "The original Girls must each confirm actual attendance after this notice: "
                + data["notice"],
            )
            return
        action = "end"
        fields = [
            Field("end", "Actual ending", (("end", "The real function has ended"),)),
            Field("account", "Describe its actual ending", paragraph=True),
        ]
    elif not data["attended"]:
        action = "attend"
        fields = [
            Field(
                "notice",
                "Notice and actual attendance",
                (("attend", "I know these rights and actually attended"),),
            ),
            Field("account", "Describe your actual attendance", paragraph=True),
        ]
    elif data["phase"] == "active":
        action = "tag"
        fields = [
            Field("tag", "Tag you give the Handler"),
            Field("account", "Describe your actual out-of-line action", paragraph=True),
        ]
    else:
        await reply(
            interaction, "Your informed attendance is saved. Waiting for the other original Girls."
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
            values.get("tag", ""),
        )
        return "Your actual function response is saved."

    form = NativeForm(
        interaction.user.id, "Political function: " + data["kind"], data["notice"], fields, submit
    )
    await reply(interaction, form.text(), form)
