"""Actual Handler body owns its corruption choice; no bot-written personnel response."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_handler_void import HandlerVoidService
from girlframe.services.onboarding import WorkflowError


async def open_handler_void(
    interaction: discord.Interaction, service: HandlerVoidService, work: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), work)
    episode = data["episode"]
    if not data["can_act"]:
        await reply(
            interaction, "This original body's source corruption is removed or its body ended."
        )
        return
    if episode["phase"] == "surgery":

        async def surgery(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.record_surgery,
                viewer_from_interaction(current),
                str(current.id),
                work,
                data["revision"],
                values["account"],
                performed=values["performed"][0] == "yes",
                removed=values["removed"][0] == "yes",
            )
            return (
                "The actual performed surgery and original body's corruption removal are recorded."
            )

        fields = [
            Field(
                "account", "Describe the actual personnel, procedure and removal", paragraph=True
            ),
            Field(
                "performed",
                "Actual procedure",
                (("yes", "Personnel actually performed this surgery"),),
            ),
            Field(
                "removed",
                "Actual removal",
                (("yes", "The source corruption was actually removed"),),
            ),
        ]
        callback = surgery
        instructions = (
            "The original Handler requested immediate surgery. Record its actual performance, "
            "personnel and removal. This does not invent their dialogue or consent, grant any "
            "other healing, or move the body; use actual physical controls for any transport first."
        )
    else:
        options: tuple[tuple[str, str], ...] = (
            ("knife", "Cut it out with your knife"),
            ("surgery", "Request immediate surgery"),
        )
        if episode["phase"] == "choice":
            options = (options[0], ("drugs", "Halt spread with experimental drugs"), options[1])

        async def choose(current: discord.Interaction, values: dict[str, Any]) -> str:
            choice = values["choice"][0]
            manifestation = values["manifestation"][0]
            if choice == "drugs" and manifestation == "none":
                raise WorkflowError("Choose the actual localized NPC-list manifestation.")
            result = await asyncio.to_thread(
                service.choose,
                viewer_from_interaction(current),
                str(current.id),
                work,
                data["revision"],
                choice,
                values["account"],
                site=values.get("site", ""),
                manifestation=None if manifestation == "none" else manifestation,
            )
            return (
                "Corruption stabilized; the original body still has localized Void "
                "and needs actual removal."
                if result["phase"] == "stabilized"
                else "Actual surgery requested. Reopen when the actual procedure occurs."
                if result["phase"] == "surgery"
                else "Your actual performed removal and its source wound are recorded."
            )

        fields = [
            Field("choice", "Your original body's response", options),
            Field("site", "Actual small body site (knife or drugs)", required=False),
            Field(
                "manifestation",
                "Drug manifestation (drugs only)",
                (
                    ("none", "Not using drugs"),
                    ("brain", "Void of the brain"),
                    ("bones", "Void of the bones"),
                    ("flesh", "Void of the flesh"),
                    ("abstract", "Void of the abstract"),
                ),
            ),
            Field("account", "Actual cut/injection, or actual surgery request", paragraph=True),
        ]
        callback = choose
        instructions = (
            "Choose for the recorded ORIGINAL Handler body. Knife and drugs record an action you "
            "actually perform and describe. A knife cuts out the corruption and leaves that actual "
            "wound; drugs only halt spread, with a local manifestation. Surgery requires a real "
            "performed-procedure record before removal. No successor body inherits this condition."
        )
        if episode["phase"] == "stabilized":
            instructions += (
                " Current localized condition: "
                + episode["manifestation"]
                + " at "
                + episode["site"]
            )
    form = NativeForm(
        interaction.user.id, "Handler: original-body Void", instructions, fields, callback
    )
    await reply(interaction, form.text(), form)
