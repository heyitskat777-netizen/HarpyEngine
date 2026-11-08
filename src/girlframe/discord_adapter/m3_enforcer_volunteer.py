"""The non-Dog Enforcer offers; the original chooser accepts an actual executor."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_enforcer_volunteer import VolunteerService
from girlframe.services.onboarding import WorkflowError


async def open_volunteer(interaction: discord.Interaction, service: VolunteerService) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.preview_volunteer, viewer)
    if not data["candidates"]:
        raise WorkflowError(
            "No actual pending Punishment is available for your source-supported offer."
        )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.volunteer,
            viewer_from_interaction(current),
            str(current.id),
            values["work"][0],
            values["account"],
        )
        return "Actual volunteer offer saved for its original chooser: " + str(result["id"])

    await NativeForm(
        viewer.user_id,
        "Volunteer for a Punishment",
        "You offer to execute the actual consequence. Its original chooser keeps the instruction "
        "and discipline debt; no assignment is silently transferred.",
        [
            Field(
                "work",
                "Actual pending consequence",
                tuple((x["id"], x["label"]) for x in data["candidates"]),
            ),
            Field("account", "Your actual offer to carry it out", paragraph=True),
        ],
        submit,
    ).present(interaction)


async def open_volunteer_offer(
    interaction: discord.Interaction, service: VolunteerService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get_offer, viewer, identity)
    if data.get("can_withdraw") and not data["can_decide"]:

        async def withdraw(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.withdraw,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["account"],
            )
            return (
                "Your unaccepted offer was withdrawn. "
                "The actual original Punishment remains pending."
            )

        await NativeForm(
            viewer.user_id,
            "Withdraw your unaccepted offer",
            "This closes only your optional offer; it fulfills no discipline debt or instruction.",
            [Field("account", "Your actual reason for withdrawing", paragraph=True)],
            withdraw,
        ).present(interaction)
        return
    if data["state"] == "resolved" or not data["can_decide"]:
        await reply(
            interaction,
            "Offer " + data["state"] + ". Its original chooser owns this executor appointment.",
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.decide,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["accept"][0] == "yes",
            values["account"],
        )
        return (
            "Actual executor offer "
            + str(result["state"])
            + ". "
            + (
                "Open its saved instruction/scene case in Requests: " + str(result["case_id"])
                if result["case_id"]
                else "The original Punishment remains pending with its original chooser."
            )
        )

    await NativeForm(
        viewer.user_id,
        "Appoint this actual volunteer?",
        "Original offer: "
        + data["body"]["account"]
        + ". You retain the actual type/details instruction; "
        "the named executor supplies actual scene attendance and effects.",
        [
            Field(
                "accept",
                "Accept the proposed actual executor?",
                (("yes", "Accept this executor"), ("no", "Decline this offer")),
            ),
            Field("account", "Your actual decision and instruction context", paragraph=True),
        ],
        submit,
    ).present(interaction)
