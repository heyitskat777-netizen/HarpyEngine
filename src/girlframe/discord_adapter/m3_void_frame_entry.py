"""Private source cards; genuine cockpit entry and mandatory real Dive remain separate."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field
from girlframe.discord_adapter.m3_memory_pages import MemoryForm, MemoryHistory
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_void_frame_entry import VoidFrameEntryService


async def open_void_frame_entry(
    interaction: discord.Interaction,
    service: VoidFrameEntryService,
    identity: str,
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.view, viewer, identity)

    async def access(current: discord.Interaction) -> None:
        await asyncio.to_thread(service.view, viewer_from_interaction(current), identity)

    if data["type"] == "arm" and data["state"] == "pending":

        async def arm(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.arm,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
                values["account"],
            )
            return (
                "The original random Girl is saved once. The obligation awaits actual Frame entry."
            )

        form = MemoryForm(
            viewer.user_id,
            "Actual Low Void source",
            "Select one random original Girl once. Reopening cannot redraw. "
            "Her next actual own-Frame entry requires real Dive Deep, with its normal Heat "
            "and an additional +1 per actual Void Asset.",
            [Field("account", "The actual Strain context", paragraph=True)],
            arm,
            authorize=access,
        )
        await reply(interaction, form.text(), form)
        return
    text = "\n".join(
        (
            "**Original next-entry Dive source**",
            "Original source account: " + clean(data.get("account", "Source already armed")),
            "State: " + clean(data.get("state", "saved")),
            "The Void-Asset bonus is additional to ordinary Heat "
            "and all actual Dive costs/outcomes.",
        )
    )
    options = []
    if data.get("can_bind"):
        options.append(("venue", "Bind my actual joined scene for the owed Dive"))
    if data.get("child_descriptor"):
        options.append(("dive", "Perform the genuine required Dive"))
    options.extend(
        ("choice:" + value, "Open my actual saved Dive response")
        for value in data.get("choices", ())
    )
    pause = data.get("pause") or {}
    if pause.get("retry"):
        options.append(("retry", "Retry the actual source scene pause"))
    if data.get("prerequisites"):
        text += "\nResolve the actual prior Void consequences in your private requests first."
    if data.get("gap"):
        text += "\nRequired source adapter: " + clean(data["gap"])
    if data.get("pause"):
        text += "\nActual source pause: " + clean(data["pause"]["state"])
    if not options:
        history = MemoryHistory(viewer.user_id, text, access)
        await reply(interaction, history.text(), history)
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        operation = values["operation"][0]
        if operation == "venue":
            await asyncio.to_thread(
                service.bind_venue,
                viewer_from_interaction(current),
                str(current.id),
                data["entry"],
                data["revision"],
                int(current.channel_id or 0),
            )
            return "Your actual source scene is bound; wait for its genuine pause."
        if operation == "retry":
            from girlframe.services.p1_source_pause import retry

            await asyncio.to_thread(
                retry,
                service.game,
                viewer_from_interaction(current),
                str(current.id),
                data["entry"],
            )
            return "The actual source pause retry is queued."
        if operation.startswith("choice:"):
            from girlframe.discord_adapter.m2_ui import open_choice

            await open_choice(current, service.game, operation.removeprefix("choice:"))
            return None
        from girlframe.discord_adapter.m2_ui import open_play

        await open_play(current, service.game, parent=data["child_descriptor"], _pilot=True)
        return None

    form = MemoryForm(
        viewer.user_id,
        "Actual required Frame-entry Dive",
        text,
        [Field("operation", "Your actual source control", tuple(options))],
        submit,
        authorize=access,
    )
    await reply(interaction, form.text(), form)
