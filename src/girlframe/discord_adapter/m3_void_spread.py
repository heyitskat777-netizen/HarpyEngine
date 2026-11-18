"""Apply the confirmed footprint and offer the original role-owned responses."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_void_spread import MANIFESTATIONS, SpreadService


async def open_application(
    interaction: discord.Interaction,
    effects: EffectService,
    data: dict[str, Any],
    identity: str,
) -> None:
    if data["state"] == "resolved":
        await reply(interaction, "The original area's effects have resolved.")
        return
    if data["spread_started"]:
        await reply(interaction, "Each affected role has its own required work in the Inbox.")
        return
    service = SpreadService(effects.strain)
    unknown = await asyncio.to_thread(service.area, viewer_from_interaction(interaction), identity)
    fields = [Field("apply", "Apply the confirmed area?", (("yes", "Apply ordinary Void gain"),))]
    if unknown:
        fields += [
            Field(
                "outside",
                "Whose absence from the area is documented?",
                unknown,
                minimum=len(unknown),
                maximum=len(unknown),
            ),
            Field("account", "Evidence that these original people were outside", paragraph=True),
        ]

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.start,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["game_revision"],
            data["revision"],
            tuple(values.get("outside", ())),
            values.get("account", ""),
        )
        count = result["required"]
        if count:
            return f"{count} original occupants have required Void work in the Inbox."
        return "The confirmed footprint had no occupants with ordinary Void rules."

    await NativeForm(
        interaction.user.id,
        "Apply the High Void spread",
        "The saved squares and original positions determine who is affected.",
        fields,
        submit,
    ).present(interaction)


async def open_gain(
    interaction: discord.Interaction,
    service: SpreadService,
    identity: str,
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if data["state"] == "resolved":
        await reply(interaction, "The original Void alteration is recorded.")
        return
    if data["external_followup"]:
        await reply(
            interaction, "The alteration is recorded. The actual transformation is required."
        )
        return
    if data["gain"]:
        await reply(interaction, "The alteration is recorded. Resolve its original threshold work.")
        return
    if data["role"] == "unsupported":
        await reply(interaction, "This original role still needs its specific Void rules.")
        return
    options = (
        tuple((x, "Void of the " + x) for x in MANIFESTATIONS)
        if data["role"] == "npc"
        else data["assets"]
    )
    if not options:
        await reply(interaction, "Recover an eligible owned Asset for this required Void gain.")
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.gain,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            values["pick"][0],
            values["account"],
        )
        return "The original Void gain is recorded. Review any required transformation."

    await NativeForm(
        interaction.user.id,
        "Resolve Void gain · " + data["actor"],
        "Choose the original character's ordinary consequence.",
        [
            Field("pick", "Choose the actual alteration", options),
            Field("account", "Describe the alteration", paragraph=True),
        ],
        submit,
    ).present(interaction)
