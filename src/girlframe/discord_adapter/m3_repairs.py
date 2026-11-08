"""Private exact-price offers and owned optional purchase controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_modular import replacement_fields, replacements
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_repairs import RepairService
from girlframe.services.onboarding import WorkflowError


def price(value: str) -> int:
    if not value.isascii() or not value.isdecimal() or len(value) > 8:
        raise WorkflowError("Enter a whole Permission price of zero or more.")
    return int(value)


async def open_quote(
    interaction: discord.Interaction, service: RepairService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    text = (
        "**Extra Asset repair**\n"
        + clean(data["asset"])
        + " — "
        + str(data["cost"])
        + " Permission(s)."
    )
    if data["may_answer"]:
        text += "\nConfirm this exact price or decline."
        if not data["available"]:
            text += " The quote needs a fresh Handler review before purchase."
        options: tuple[tuple[str, str], ...] = (
            (("accept", "Pay this price and repair this Asset"),) if data["available"] else ()
        )
        options += (("decline", "Decline this offer"),)

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            chosen = replacements(values)
            result = await asyncio.to_thread(
                service.respond,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["game_revision"],
                data["revision"],
                values["answer"][0] == "accept",
                replacement=chosen[0] if chosen else None,
            )
            return "Repair offer " + str(result["state"]) + "."

        form = NativeForm(
            viewer.user_id,
            "Review repair price",
            text,
            [Field("answer", "Your response", options)] + replacement_fields(data["modular"], 1),
            submit,
        )
        await reply(interaction, form.text(), form)
    elif data["may_reprice"]:

        async def reprice(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.offer,
                viewer_from_interaction(current),
                str(current.id),
                data["game_revision"],
                data["period"],
                data["owner"],
                data["asset_id"],
                price(values["cost"]),
                identity,
                data["revision"],
            )
            return "The revised price is saved. The player must give a new response."

        form = NativeForm(
            viewer.user_id,
            "Revise repair price",
            text,
            [Field("cost", "New price in Permissions")],
            reprice,
        )
        await reply(interaction, form.text(), form)
    else:
        await reply(interaction, text + "\nState: " + data["state"])


async def open_repairs(interaction: discord.Interaction, service: RepairService) -> None:
    viewer = viewer_from_interaction(interaction)
    quotes = await asyncio.to_thread(service.list, viewer)
    options = tuple((x["id"], x["label"][:75] + " — " + x["state"]) for x in quotes)
    eligible: dict[str, Any] | None = None
    try:
        eligible = await asyncio.to_thread(service.eligible, viewer)
    except WorkflowError:
        pass
    if eligible and eligible["assets"]:
        options = (("offer", "Quote one damaged Asset after shortage recovery"),) + options
    if not options:
        await reply(
            interaction,
            "No current extra-repair offer is available. "
            "The Handler quotes each repair after shortage recovery.",
        )
        return

    async def choose(current: discord.Interaction, token: str) -> None:
        if token != "offer":
            await open_quote(current, service, token)
            return
        assert eligible is not None
        entries = {str(i): row for i, row in enumerate(eligible["assets"])}

        async def submit(actor: discord.Interaction, values: dict[str, Any]) -> str:
            asset = entries[values["asset"][0]]
            await asyncio.to_thread(
                service.offer,
                viewer_from_interaction(actor),
                str(actor.id),
                eligible["game_revision"],
                eligible["period"],
                asset["owner"],
                asset["asset"],
                price(values["cost"]),
            )
            return "Price offered. The player can review it in requests or /mission repairs."

        form = NativeForm(
            viewer.user_id,
            "Offer extra repair",
            "Quote one exact price. This spends no Permissions.",
            [
                Field(
                    "asset",
                    "Damaged Asset",
                    tuple(
                        (key, row["callsign"][:35] + " — " + row["name"][:60])
                        for key, row in entries.items()
                    ),
                ),
                Field("cost", "Price in Permissions"),
            ],
            submit,
        )
        await reply(current, form.text(), form)

    await Picker(viewer.user_id, "**Extra repairs and price offers**", options, choose).show(
        interaction
    )
