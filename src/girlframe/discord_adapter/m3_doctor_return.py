"""Reopenable private engineer packages; the original donor confirms the destination."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_memory_pages import paginate
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_doctor_return import ReturnService


async def open_return(
    interaction: discord.Interaction, service: ReturnService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    loan = data["loan"]
    summary = "Borrowed Wings — " + (
        "returned" if data["state"] == "resolved" else "return pending"
    )
    summary += "\nOriginal component: " + clean(loan["asset"])
    summary += "\nOriginal donor's receiving Frame: " + clean(
        str(data["destination_frame"] or "awaiting a real Frame")
    )
    if data["custody"]:
        summary += "\nActual custody: " + clean(data["custody"]["actor"]["entity"])
        asset = data["custody"]["asset"]
        summary += (
            " — "
            + clean(asset["name"])
            + ("; damaged" if asset["damaged"] else "; undamaged")
            + ("; Void" if asset["void"] else "")
        )
    if data["blocked"]:
        summary += "\n" + clean(data["blocked"])
    package = data["package"]
    if package:
        summary += "\nExact receiving Frame ID: " + clean(package["frame"])
        summary += "\nEngineer access/recovery and package: " + clean(package["account"])
        if package["replace"]:
            summary += "\nExplicit cap replacement: " + clean(package["replace"])
    pages = paginate(summary, "Borrowed Wings return")
    if data["state"] == "resolved":
        await reply(interaction, pages[0].content)
        for page in pages[1:]:
            await interaction.followup.send(
                page.content, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
            )
        return
    options = [("refresh", "Reopen current custody and saved package")]
    if data["can_quote"]:
        options.append(("quote", "Record exact engineer return package"))
    if data["can_confirm"]:
        options.append(("confirm", "Confirm my exact receiving Frame and return"))

    async def choose(current: discord.Interaction, choice: str) -> None:
        if choice == "refresh":
            await open_return(current, service, identity)
            return
        if choice == "confirm":
            await asyncio.to_thread(
                service.confirm,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
            )
            await open_return(current, service, identity)
            return

        async def submit(form_interaction: discord.Interaction, values: dict[str, Any]) -> str:
            selected = values["replace"][0]
            await asyncio.to_thread(
                service.quote,
                viewer_from_interaction(form_interaction),
                str(form_interaction.id),
                identity,
                data["revision"],
                data["game_revision"],
                values["account"],
                replace=None if selected == "none" else selected,
            )
            return (
                "Exact engineer package saved. The original donor can reopen "
                "this Inbox entry and confirm its actual receiving Frame."
            )

        await NativeForm(
            current.user.id,
            "Wings engineer return package",
            "Record actual access/recovery and the current original donor's receiving Frame; "
            "the donor must confirm the saved package.",
            [
                Field(
                    "replace",
                    "Cap replacement, only if needed",
                    (("none", "No replacement"),)
                    + tuple((x["id"], x["name"]) for x in data["replacements"]),
                ),
                Field("account", "Actual access, recovery and destination", paragraph=True),
            ],
            submit,
        ).present(current)

    await Picker(interaction.user.id, pages[0].content, tuple(options), choose).show(interaction)
    for page in pages[1:]:
        await interaction.followup.send(
            page.content, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )
