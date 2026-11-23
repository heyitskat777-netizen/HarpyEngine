"""Native owned rolling and column selection for named Strain tracks."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_named_strain import NamedStrainService


async def open_named_strain(
    interaction: discord.Interaction, service: NamedStrainService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.view, viewer, identity)
    label = clean(data["track"])
    face = data["face"]
    if data["status"] == "resolved":
        await reply(interaction, f"{label} rolled {face}. Column {data['column']} took effect.")
        return
    options: tuple[tuple[str, str], ...]
    if face is None:
        options = (("roll", "Roll once"),)
        prompt = "Roll this track’s d6"
        scope = ""
    else:
        options = tuple((str(i), x.title) for i, x in enumerate(data["options"], 1))
        prompt = "Choose a column"
        scope = f"Saved d6 · {face}"

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        chosen = values["option"][0]
        result = await asyncio.to_thread(
            service.advance,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            data["work_revision"],
            None if chosen == "roll" else int(chosen),
        )
        if result["column"] is None:
            return f"Saved d6 · {result['face']}. Reopen this track to choose a column."
        return "The selected event took effect."

    await NativeForm(
        viewer.user_id,
        label,
        scope,
        [Field("option", prompt, options)],
        submit,
    ).present(interaction)
