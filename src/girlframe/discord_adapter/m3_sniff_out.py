"""Private native controls for the original Sniff You Out search."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_sniff_out import SniffOutService


async def open_search(
    interaction: discord.Interaction,
    service: SniffOutService,
    identity: str,
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if "found" in data:
        await reply(interaction, "Your original search identified " + data["found"] + ".")
        return
    if "targets" in data and data["targets"]:
        step, text = "offer", "Seal the actual hidden source and describe the investigator’s lead."
        fields = [
            Field("selected", "Actual Gorgon and guise", tuple(data["targets"].items())),
            Field("account", "What the investigating Girl has learned so far", paragraph=True),
        ]
    elif "heat" in data:
        step, text = "roll", data["hook"]
        fields = [Field("heat", f"Your Heat spend (available: {data['heat']})")]
    elif data.get("review"):
        step, text = "discover", data["bait_account"]
        fields = [Field("account", "Describe the actual encounter", paragraph=True)]
    elif data.get("tier") == "mid" and not data["bait"]:
        step, text = "bait", "You can volunteer your own Girl as bait to draw the Gorgon out."
        fields = [Field("account", "Describe how you serve as bait", paragraph=True)]
    else:
        await reply(
            interaction, "The search holds its original state and awaits its actual next step."
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        heat = values.get("heat", "").strip()
        if step == "roll" and (not heat.isascii() or not heat.isdecimal() or len(heat) > 9):
            return "Enter a whole amount of your available Heat."
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            step,
            selected=(values.get("selected") or ("",))[0],
            account=values.get("account", ""),
            heat=int(heat) if step == "roll" else None,
        )
        return "The original private search updated."

    form = NativeForm(interaction.user.id, "Sniff You Out", text, fields, submit)
    await reply(interaction, form.text(), form)
