"""Private Endgame leave and original-table choices."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_void_leave import LeaveService
from girlframe.services.onboarding import WorkflowError


async def open_leave(
    interaction: discord.Interaction, service: LeaveService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.view, viewer, identity)
    if leave := data["leave"]:
        await reply(interaction, clean(leave.home) + f" · Quadrant {leave.quadrant}")
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        quadrant = values["quadrant"].strip()
        if not quadrant.isascii() or not quadrant.isdecimal() or len(quadrant) > 5:
            raise WorkflowError("Enter the actual destination’s Quadrant number.")
        bond = values["bond"][0]
        await asyncio.to_thread(
            service.approve,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            data["game_revision"],
            values["home"],
            int(quadrant),
            values["account"],
            bond=None if bond == "your-hometown" else bond,
        )
        return "Leave is reserved for this Off-Duty period."

    await NativeForm(
        viewer.user_id,
        "Take leave outside Quadrant 12",
        "",
        [
            Field(
                "bond",
                "Where are you going?",
                (("your-hometown", "Your hometown"),) + data["bonds"],
            ),
            Field("home", "Name of the hometown or home"),
            Field("quadrant", "Destination Quadrant"),
            Field("account", "Describe how you spend your leave", paragraph=True),
        ],
        submit,
    ).present(interaction)


async def open_poll(interaction: discord.Interaction, service: LeaveService, identity: str) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.followup, viewer, identity)
    if data["decision"]:
        label = (
            "The campaign continues."
            if data["decision"] == "continue"
            else "The table drew this campaign to a close."
        )
        await reply(interaction, label)
        return
    is_handler = data["decision_owner"]
    if is_handler and len(data["votes"]) < data["voters"]:
        await reply(interaction, f"{len(data['votes'])} of {data['voters']} players have replied.")
        return
    if not is_handler and data["votes"]:
        await reply(interaction, "Your private preference is saved.")
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            values["preference"][0],
        )
        return (
            "The table’s decision is saved." if is_handler else "Your private preference is saved."
        )

    continue_votes = sum(x.preference == "continue" for x in data["votes"])
    await NativeForm(
        viewer.user_id,
        "Decide the campaign’s future" if is_handler else "Would you like to continue?",
        f"Continue · {continue_votes}\nClose · {len(data['votes']) - continue_votes}"
        if is_handler
        else "",
        [
            Field(
                "preference",
                "Choose an outcome",
                (("continue", "Continue"), ("close", "Draw to a close")),
            )
        ],
        submit,
    ).present(interaction)
