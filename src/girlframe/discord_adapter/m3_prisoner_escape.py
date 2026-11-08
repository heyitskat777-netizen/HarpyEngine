"""Actual source/custody/performer controls, without automatic NPC or Strain outcomes."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field
from girlframe.discord_adapter.m3_memory_pages import MemoryForm, MemoryHistory
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_prisoner_escape import PrisonerEscapeService


async def open_prisoner_escape(
    interaction: discord.Interaction,
    service: PrisonerEscapeService,
    identity: str,
) -> None:
    viewer = viewer_from_interaction(interaction)
    shown = await asyncio.to_thread(service.view, viewer, identity)

    async def access(current: discord.Interaction) -> None:
        await asyncio.to_thread(service.view, viewer_from_interaction(current), identity)

    if shown["type"] == "start":
        if shown["state"] != "pending" or not shown["candidates"]:
            await reply(
                interaction,
                "Use an actual introduced Foundation prisoner with genuine custody and "
                "a joined role. Other custody sources need their own real adapter.",
            )
            return
        candidates = {x["id"]: x for x in shown["candidates"]}

        async def start(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.start,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                shown["work_revision"],
                shown["revision"],
                int(current.channel_id or 0),
                ActorRef.model_validate(candidates[values["prisoner"][0]]["actor"]),
                values["account"],
            )
            return (
                "The actual breakout attempt and custody release are recorded. "
                "No movement or outcome was invented. Reopen this source to continue."
            )

        form = MemoryForm(
            viewer.user_id,
            "Actual prisoner breakout",
            "Choose the original held NPC in this actual scene. Their controller authors "
            "any actual movement; Girls use real supported performances to deal with them.",
            [
                Field(
                    "prisoner",
                    "Actual held prisoner",
                    tuple((x["id"], x["label"]) for x in shown["candidates"]),
                ),
                Field("account", "The actual compulsory breakout attempt", paragraph=True),
            ],
            start,
            authorize=access,
        )
        await reply(interaction, form.text(), form)
        return
    text = "\n".join(
        (
            "**Actual prisoner escape**",
            "Original prisoner: " + clean(shown["prisoner"]),
            "Original attempt: " + clean(shown["account"]),
            "State: " + clean(shown["state"]),
        )
    )
    if shown["outcome_account"]:
        text += "\nActual finding: " + clean(shown["outcome_account"])
    options = []
    if shown["can_move"]:
        options.append(("move", "Open my actual prisoner movement controls"))
    options.extend(("held:" + grip["id"], grip["label"]) for grip in shown["grips"])
    if shown["can_fail"]:
        options.extend(
            ("failed:" + value["id"], "Record factual outcome: " + value["label"])
            for value in shown["movements"]
        )
    if not options:
        history = MemoryHistory(viewer.user_id, text, access)
        await reply(interaction, history.text(), history)
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        token = values["operation"][0]
        if token == "move":
            from girlframe.discord_adapter.m3_movement import open_movement
            from girlframe.services.m3_movement import MovementService

            await open_movement(current, MovementService(service.game))
            return None
        if token.startswith("held:"):
            grip = next(x for x in shown["grips"] if x["id"] == token.removeprefix("held:"))
            await asyncio.to_thread(
                service.record_dealt,
                viewer_from_interaction(current),
                str(current.id),
                shown["id"],
                shown["revision"],
                grip["action"],
                grip["id"],
                values.get("account", ""),
            )
            return "Your actual completed performance and still-active hold resolve this attempt."
        await asyncio.to_thread(
            service.resolve_failure,
            viewer_from_interaction(current),
            str(current.id),
            shown["id"],
            shown["revision"],
            token.removeprefix("failed:"),
            values.get("account", ""),
        )
        return "Your actual factual failure and real Rebellion increase are saved once."

    form = MemoryForm(
        viewer.user_id,
        "Actual escape performance/outcome",
        text,
        [
            Field("operation", "Your actual source control", tuple(options)),
            Field(
                "account",
                "Actual finding/performance (not needed to open movement)",
                paragraph=True,
                required=False,
            ),
        ],
        submit,
        authorize=access,
    )
    await reply(interaction, form.text(), form)
