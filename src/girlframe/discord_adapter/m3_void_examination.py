"""Private original-patient confirmation for a required Low Void examination."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_void_examination import ExaminationService


async def open_exam(
    interaction: discord.Interaction, service: ExaminationService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if data["state"] != "pending":
        await reply(interaction, "This examination has already been recorded.")
        return
    fields = [Field("account", "What did the completed examination find?", paragraph=True)]
    if data["assets"]:
        # Discord limits one selector to 25 options. A Girl cannot normally hold this many.
        assets = tuple(data["assets"])
        for start in range(0, len(assets), 25):
            group = assets[start : start + 25]
            fields.append(
                Field(
                    f"found_{start}",
                    "Void Assets actually found",
                    group,
                    0,
                    len(group),
                    required=False,
                )
            )

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.finish,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            data["game_revision"],
            tuple(
                asset
                for k, entries in values.items()
                if k.startswith("found_")
                for asset in entries
            ),
            values["account"],
        )
        return "Your examination outcome is saved."

    await NativeForm(
        interaction.user.id,
        "Your medical examination",
        "Record the examination. Select the findings you are disclosing to the examiner.",
        fields,
        submit,
    ).present(interaction)
