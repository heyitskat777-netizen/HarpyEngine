"""Native private controls for source-specific mission-end reactions."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_reactions import ReactionService
from girlframe.services.onboarding import WorkflowError

KINDS = ("doctor_obsolescence", "princess_mission_end", "doctor_frame_replacement")


async def open_reaction(
    interaction: discord.Interaction, service: ReactionService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if data["kind"] == "doctor_frame_replacement":
        from girlframe.discord_adapter.m3_replacement import open_replacement
        from girlframe.services.m3_replacement import ReplacementService

        await open_replacement(interaction, ReplacementService(service.missions), identity)
        return
    if data["state"] == "resolved" or data["owner_id"] != str(viewer.user_id):
        await reply(
            interaction,
            clean(data["callsign"])
            + ": "
            + data["state"]
            + ". The assigned Handler reviews this mission-end reaction.",
        )
        return
    if data["kind"] == "doctor_obsolescence":
        instructions = (
            "The Cadre failed a mission. Planned Obsolescence requires one marked box. "
            f"Current track: {data['obsolescence_marked']}/8. A full track scraps the Frame "
            "and requires its owner to choose a replacement before continuing."
        )
        fields = [
            Field(
                "confirm", "Confirm this printed reaction", (("yes", "Mark one Obsolescence box"),)
            )
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.doctor,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
            )
            return "Marked once. " + (
                "Frame replacement is now required."
                if result["replacement_required"]
                else "Reopen /mission inbox for remaining work and rewards."
            )
    elif data["kind"] == "princess_mission_end":
        instructions = (
            "Review the actual off-duty standards condition before applying its benefit.\n"
        )
        instructions += "\n".join(
            clean(x["role"].replace("_", " "))
            + ": "
            + clean(x["label"])
            + (" (counts as an order)" if x["is_order"] else "")
            for x in data["standards"]
        )
        if not data["ruling_ready"]:
            instructions += (
                "\nThe Permission timing ruling is pending; the upheld branch remains unavailable."
            )
        fields = [
            Field(
                "upheld",
                "Were the standards upheld?",
                (
                    ("yes", "Yes — apply the source benefit"),
                    ("no", "No — the benefit does not apply"),
                ),
            ),
            Field("rationale", "Brief factual standards review", paragraph=True),
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.princess,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
                upheld=values["upheld"][0] == "yes",
                rationale=values["rationale"],
            )
            return (
                "Standards review saved. Reopen /mission inbox before committing "
                "the final mission rewards."
            )
    else:
        raise WorkflowError("This reaction needs its specific supported resolver.")
    form = NativeForm(
        viewer.user_id, "Mission-end reaction — " + data["callsign"], instructions, fields, submit
    )
    await reply(interaction, form.text(), form)


async def reaction_queue(interaction: discord.Interaction, service: ReactionService) -> None:
    viewer = viewer_from_interaction(interaction)
    rows = await asyncio.to_thread(service.missions.owned_work, viewer)
    options = tuple(
        (row["id"], row["kind"].replace("_", " ").title() + " — Player " + row["subject_id"])
        for row in rows
        if row["kind"] in KINDS
    )
    if not options:
        await reply(interaction, "No mission-end playbook reactions are assigned to you.")
        return

    async def choose(current: discord.Interaction, identity: str) -> None:
        await open_reaction(current, service, identity)

    view = Picker(viewer.user_id, "**Mission-end playbook reactions**", options, choose)
    await view.show(interaction)
