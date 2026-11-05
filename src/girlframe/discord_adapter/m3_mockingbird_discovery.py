"""Actual source participants report discovery; actual witness and Handler answer separately."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_mockingbird_discovery import DiscoveryService
from girlframe.services.onboarding import WorkflowError


async def open_exposure(
    interaction: discord.Interaction, service: DiscoveryService, identity: str
) -> None:
    if interaction.channel_id is None:
        raise WorkflowError("Declare actual discovery in the witness's current source scene")
    channel = interaction.channel_id
    data = await asyncio.to_thread(
        service.preview, viewer_from_interaction(interaction), identity, channel
    )
    if not data["witnesses"]:
        raise WorkflowError("Cast the actual witness in this source scene first")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        role = next(x for x in data["witnesses"] if x["token"] == values["witness"][0])
        result = await asyncio.to_thread(
            service.report,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            channel,
            ActorRef.model_validate(role["ref"]),
            values["account"],
        )
        return (
            "Discovery declaration saved: "
            + str(result["id"])
            + ". The actual witness must attest it before any Handler consequence."
        )

    await NativeForm(
        interaction.user.id,
        "Report actual discovery",
        "This private exposure creates no automatic discovery or Punishment. "
        "Declare only what an actual person found out; they must confirm their own source facts.",
        [
            Field(
                "witness",
                "Actual witness in this source scene",
                tuple((x["token"], x["label"]) for x in data["witnesses"]),
            ),
            Field("account", "What did this actual witness find out, and how?", paragraph=True),
        ],
        submit,
    ).present(interaction)


async def open_discovery(
    interaction: discord.Interaction, service: DiscoveryService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    body = data["body"]
    if not data["can_witness"] and not data["can_handler"]:
        await reply(
            interaction,
            "Your actual source discovery: " + body["phase"] + ".\n" + clean(body["account"]),
        )
        return
    fields = [
        Field(
            "accept",
            "Did this actual source discovery occur?",
            (("yes", "Confirm actual finding"), ("no", "Not established / decline declaration")),
        ),
        Field("account", "Describe your own actual source confirmation", paragraph=True),
    ]
    if data["can_handler"] and data["kind"] == "low_tag":
        fields.append(
            Field(
                "tag", "If confirmed: your actual Tag for the original counterpart", required=False
            )
        )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            body["revision"],
            values["accept"][0] == "yes",
            values["account"],
            tag=values.get("tag", ""),
        )
        return "Your actual discovery response is saved: " + str(result["phase"]) + ". "

    await NativeForm(
        interaction.user.id,
        "Your owned discovery response",
        clean(body["account"]) + "\nA private backend view is not fictional knowledge. "
        "Only actual discovery triggers the printed conditional Tag. "
        "Risk of Punishment is not an automatic sentence.",
        fields,
        submit,
    ).present(interaction)
