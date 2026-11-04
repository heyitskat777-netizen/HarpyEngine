"""Private initial-position dropdowns and distinct actual facilitator review."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.services.m3_physical import PhysicalService

MODES = (
    ("outside_frame", "Outside my Frame"),
    ("inside_frame", "Inside its cockpit, not piloting"),
    ("piloting", "Piloting my actual Frame"),
)


async def open_initial(interaction: discord.Interaction, service: PhysicalService) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.preview, viewer)
    if data["pending_id"] is not None:
        await open_review(interaction, service, data["pending_id"])
        return
    if data["placement"] is not None:
        placement = data["placement"]
        text = "**Your recorded physical facts**\nGirl's map cell: " + str(
            tuple(placement["girl_cell"])
        )
        text += "\nRecorded occupancy: " + dict(MODES)[placement["mode"]]
        text += "\nRecorded Frame cell: " + str(tuple(placement["frame_cell"]))
        if data["frame_instance"] != placement["frame_instance"]:
            text += "\nThis record refers to your earlier Frame. "
            text += "Your current Frame's position awaits its own source."
        await reply(interaction, text + "\nInitial physical recording is complete.")
        return
    locations = {x["id"]: x for x in data["locations"]}
    if not locations:
        await reply(
            interaction, "The actual campaign map needs to be initialized before physical setup."
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.propose,
            viewer_from_interaction(current),
            str(current.id),
            data["game_revision"],
            InitialPlacement(
                actor=ActorRef.model_validate(data["actor"]),
                frame_instance=data["frame_instance"],
                girl_cell=tuple(locations[values["girl_location"][0]]["cell"]),
                frame_cell=tuple(locations[values["frame_location"][0]]["cell"]),
                mode=values["mode"][0],
                account=values["account"],
                facts_confirmed=True,
            ),
        )
        return (
            "Your original physical facts are saved for facilitator review. "
            "Reopen /character requests. Request: " + str(result["id"])
        )

    options = tuple((key, x["name"]) for key, x in locations.items())
    form = NativeForm(
        viewer.user_id,
        "Record original physical facts",
        "Propose your actual current body and Frame positions for facilitator review. "
        "Choose your actual occupancy. While inside, the Girl and Frame share a map cell.",
        [
            Field("girl_location", "Where is your Girl?", options),
            Field("frame_location", "Where is your actual assigned Frame?", options),
            Field("mode", "Your actual Frame occupancy", MODES),
            Field("account", "Describe the actual physical facts", paragraph=True),
            Field(
                "confirm",
                "Confirm these actual facts for review",
                (("yes", "Save my original factual proposal"),),
            ),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_review(
    interaction: discord.Interaction, service: PhysicalService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    body, proposal = data["review"], data["review"]["proposal"]
    text = "**Original physical facts: " + clean(body["label"]) + "**\n"
    text += (
        "Girl's cell: "
        + str(tuple(proposal["girl_cell"]))
        + "\nFrame's cell: "
        + str(tuple(proposal["frame_cell"]))
    )
    text += "\nOccupancy: " + dict(MODES)[proposal["mode"]] + "\n" + clean(proposal["account"])
    if data["state"] == "resolved":
        await reply(
            interaction,
            text + "\nReview: " + clean(body["decision"]) + "\n" + clean(body["response"]),
        )
        return
    decisions = (
        (
            ("accept", "Confirm these actual original facts"),
            ("decline", "Decline this factual proposal"),
        )
        if data["can_review"]
        else (("withdraw", "Withdraw my pending proposal"),)
    )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.decide,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["decision"][0],
            values["account"],
        )
        return "Original physical review saved: " + str(result["decision"]) + "."

    form = NativeForm(
        viewer.user_id,
        "Review actual physical facts",
        text,
        [
            Field("decision", "Your own review action", decisions),
            Field("account", "Your actual response", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
