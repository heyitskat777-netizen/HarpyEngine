"""Owned mandatory Tag rebuilding and private original Identity-removal history."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_disposable_psyche import TagSelection
from girlframe.services.m3_disposable_psyche import PsycheService


async def open_psyche(
    interaction: discord.Interaction, service: PsycheService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity is None:
        data = await asyncio.to_thread(service.menu, viewer)
        if not data["tasks"]:
            await reply(
                interaction,
                "No saved Disposable Psyche source. Removal is selected when "
                "actually marking an eligible Identity; rebuilding follows actual Go OffDuty.",
            )
            return

        async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
            await open_psyche(current, service, values["source"][0])
            return None

        form = NativeForm(
            viewer.user_id,
            "Disposable Psyche",
            "Your original sources and required rebuilding.",
            [
                Field(
                    "source",
                    "Your saved source",
                    tuple((x["id"], x["label"] + " (" + x["phase"] + ")") for x in data["tasks"]),
                )
            ],
            choose,
        )
        await reply(interaction, form.text(), form)
        return
    data = await asyncio.to_thread(service.view, viewer, identity)
    if data["phase"] == "removed":
        await reply(
            interaction,
            "Removed Identity: "
            + data["identity"]
            + ". Ordinary Heat: "
            + str(data["gain"])
            + "; additional Heat: "
            + str(data["extra"])
            + "; actual Heat spent: "
            + str(data["spent"])
            + ".",
        )
        return
    if data["phase"] == "converted":
        await reply(
            interaction,
            "Actual converted Identities: "
            + ", ".join(data["identities"])
            + ". Your other marks and resources remain recorded.",
        )
        return
    if data["phase"] == "no_tags":
        await reply(
            interaction,
            "Your actual Go OffDuty source had no Tags to turn into Identities. "
            "No Tags or Identities were invented.",
        )
        return
    if not data["tags"]:
        await reply(
            interaction,
            "Your original mandatory Tag conversion remains pending. Its original Tags are "
            "currently unavailable; recover the actual source before proceeding.",
        )
        return
    fields = [
        Field(
            "tags",
            "Turn actual Tags into Identities",
            tuple((x["id"], x["label"]) for x in data["tags"]),
            maximum=min(4, len(data["tags"])),
        )
    ]
    if data["identities"]:
        fields.append(
            Field(
                "replace",
                "Only if required by the four-Identity cap",
                tuple((x["id"], x["label"]) for x in data["identities"]),
                minimum=0,
                maximum=min(4, len(data["identities"])),
                required=False,
            )
        )

    async def convert(current: discord.Interaction, values: dict[str, Any]) -> str:
        replacements = values.get("replace", ())
        selections = tuple(
            TagSelection(
                tag=tag, replace=replacements[index] if index < len(replacements) else None
            )
            for index, tag in enumerate(values["tags"])
        )
        await asyncio.to_thread(
            service.convert,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            selections,
        )
        return (
            "Your selected actual Tags became Identities. This required source is complete; "
            "ordinary recovery and other period work keep their own controls."
        )

    form = NativeForm(
        viewer.user_id,
        "Disposable Psyche: rebuild",
        "Choose one to four actual Tags. "
        "Your current ordinary Identity count is "
        + str(data["count"])
        + ". Replace exactly as many existing eligible Identities "
        "as the four-Identity cap requires; otherwise select none. Labels come from the real Tags. "
        "Owed Tag work must finish first.",
        fields,
        convert,
    )
    await reply(interaction, form.text(), form)
