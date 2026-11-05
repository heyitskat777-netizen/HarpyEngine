"""Native paid NPC relationship and actual participant-owned treatment controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_physiotherapist import PhysiotherapistService
from girlframe.services.onboarding import WorkflowError


async def open_purchase(interaction: discord.Interaction, service: PhysiotherapistService) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction))
    if not data["available"]:
        raise WorkflowError("No reviewed native Priestess Physiotherapist source is available")
    if data["requests"]:
        await open_request(interaction, service, data["requests"][-1])
        return
    if data["owned"] or not data["npcs"]:
        await reply(
            interaction,
            "Introduce a real living NPC through World setup under their actual "
            "human controller first. This purchase never assigns another human or invents consent.",
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> None:
        saved = await asyncio.to_thread(
            service.buy,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            values["npc"][0],
            values["account"],
        )
        await open_request(current, service, saved["id"])

    await NativeForm(
        interaction.user.id,
        "Void Physiotherapist — 2 Permissions",
        "Gain a Personal NPC Bond after their actual controller confirms this relationship and "
        "knowledge of Void leakage. No acceptance is supplied for them.",
        [
            Field(
                "npc",
                "Actual physiotherapist NPC",
                tuple((x["id"], x["label"]) for x in data["npcs"]),
            ),
            Field("account", "Your actual relationship proposal", paragraph=True),
        ],
        submit,
    ).present(interaction)


async def open_request(
    interaction: discord.Interaction, service: PhysiotherapistService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    value = data["therapy"]
    if value["phase"] == "bond":
        if not data["controller"]:
            await reply(
                interaction,
                "Paid relationship saved. The actual NPC controller must confirm "
                "the Personal Bond and their character's knowledge of Void leakage in their inbox.",
            )
            return
        operation, fields = (
            "accept",
            [Field("account", "Confirm your NPC relationship and expertise", paragraph=True)],
        )
        instructions = (
            value["relationship"] + "\nConfirm only your own actual NPC's Personal Bond "
            "and Void physiotherapy expertise."
        )
    elif value["phase"] == "scene":
        if not data["controller"]:
            await reply(
                interaction,
                "Your actual therapy scene and requested removal are saved. "
                "The original NPC controller must confirm attendance and actual treatment.",
            )
            return
        operation, fields = (
            "treat",
            [
                Field("tag", "The Tag your actual NPC gives the Girl"),
                Field(
                    "account", "Record actual attendance and completed treatment", paragraph=True
                ),
            ],
        )
        selected = next(
            (x["label"] for x in data["assets"] if x["id"] == value["asset"]),
            "No Void removal" if value["asset"] is None else "Original Asset unavailable; reopen",
        )
        instructions = (
            value["scene"]["summary"]
            + "\nRequested treatment: "
            + selected
            + "\nConfirm your own actual attendance, give a Tag "
            "and record the requested treatment. The Asset is preserved; damage is unchanged."
        )
    elif data["patient"] and data["period"] is not None:
        operation = "scene"
        fields = [
            Field(
                "location",
                "Actual surviving scene location",
                tuple((x["id"], x["label"]) for x in data["locations"]),
            ),
            Field(
                "asset",
                "Remove permanent Void from one Asset, or decline removal",
                (("none", "No Void removal"),)
                + tuple((x["id"], x["label"]) for x in data["assets"]),
            ),
            Field("account", "Describe your actual Off-Duty scene with this NPC", paragraph=True),
        ]
        instructions = (
            "Both actual roles must already be in this open scene. Recording it does not "
            "move anyone or supply the other human's attendance. "
            "Stored conditional Void is separate."
        )
    else:
        await reply(
            interaction,
            "Relationship saved. Start an actual Off-Duty scene with this NPC "
            "from the patient's Requisitions menu. Completed treatment remains in source history.",
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        chosen = values.get("asset", ("none",))[0]
        saved = await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            data["game_revision"],
            operation=operation,
            account=values["account"],
            channel=interaction.channel_id if operation == "scene" else None,
            location=values.get("location", ("",))[0],
            asset=None if chosen == "none" else chosen,
            tag=values.get("tag", ""),
        )
        return (
            "Actual therapy scene closed. NPC-given Tag and any chosen Void removal are saved."
            if saved["phase"] == "closed"
            else "Your actual owned response is saved; reopen the menu or inbox."
        )

    await NativeForm(
        interaction.user.id, "Void Physiotherapist", instructions, fields, submit
    ).present(interaction)
