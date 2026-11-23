"""Native private Inbox form for a printed local NPC care move."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_npc_care import JOBS, NpcCareService


async def open_care(
    interaction: discord.Interaction, service: NpcCareService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    experiment = data["job"] == "scientist"
    if "targets" in data:
        text = "Choose an actual local recipient and describe what your NPC offers."
        fields = [
            Field("target", "Actual recipient", tuple(data["targets"].items())),
            Field("account", "Describe the care your NPC offers", paragraph=True),
        ]
    else:
        text = clean(data["account"])
        assets = tuple((f"asset/{key}", name) for key, name in data["assets"].items())
        fields = [Field("care", "Your choice", assets + (("decline", "Decline care"),))]
        if experiment:
            fields.append(
                Field(
                    "alteration", "Describe the change if accepted", paragraph=True, required=False
                )
            )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        choice = (values.get("care") or ("",))[0]
        result = await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            target=values["target"][0] if values.get("target") else None,
            account=values.get("account", ""),
            asset=choice.removeprefix("asset/") if choice.startswith("asset/") else None,
            alteration=values.get("alteration", ""),
        )
        if result["pending"]:
            return "The private care offer is saved."
        if experiment and result["void_asset"]:
            return "The original Girl gained Void. Check your Inbox for any threshold."
        if experiment and result["resisted"]:
            return "The original Girl resisted the Void change."
        return (
            "The damaged Asset was repaired." if result["repaired"] else "You declined the offer."
        )

    form = NativeForm(interaction.user.id, JOBS[data["job"]][1], text, fields, submit)
    await reply(interaction, form.text(), form)
