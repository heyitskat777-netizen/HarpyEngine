"""Actual known-NPC accusation, explicit superior-rank fact and innocence evidence."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_enforcer import EnforcerService


async def open_conditioning(interaction: discord.Interaction, service: EnforcerService) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.preview, viewer)
    if not data["targets"]:
        await reply(interaction, "No actual known free NPC is available for this accusation.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        target = next(x for x in data["targets"] if x["id"] == values["target"][0])
        if values["operation"] == ("rank",):
            await asyncio.to_thread(
                service.request_rank,
                viewer_from_interaction(current),
                str(current.id),
                target["id"],
            )
            return "Your factual rank request is with the Handler. No arrest occurred."
        if target["rank"] is None:
            return "Request the actual factual rank first. No arrest occurred."
        await asyncio.to_thread(
            service.accuse,
            viewer_from_interaction(current),
            str(current.id),
            target["id"],
            target["rank"],
            data["expected"],
            values.get("account", ""),
        )
        return (
            "Your actual accusation caused Foundation detention until innocence is proved. "
            "The NPC's current prison location is unknown; no map coordinate was invented."
        )

    form = NativeForm(
        viewer.user_id,
        "Obedience Conditioning",
        "The Foundation treats a non-Dog Enforcer as trusted. Your Handler keeps her own judgment. "
        "An actual non-superior NPC accusation causes confinement, not proof of guilt.",
        [
            Field(
                "target", "Actual known NPC", tuple((x["id"], x["name"]) for x in data["targets"])
            ),
            Field(
                "operation",
                "Your actual decision",
                (("rank", "Request factual rank"), ("accuse", "Accuse of rebel activity")),
            ),
            Field(
                "account", "Your concrete rebel-activity allegation", paragraph=True, required=False
            ),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_enforcer_task(
    interaction: discord.Interaction, service: EnforcerService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if data["state"] == "resolved" or not data["can_decide"]:
        await reply(
            interaction,
            "Your actual source-bound request is saved. "
            "The current Handler records factual rank or actual evidence of innocence.",
        )
        return
    if data["kind"] == "enforcer_rank":
        fields = [
            Field(
                "superior",
                "Actual NPC rank relative to the original Girl",
                (("yes", "A superior officer"), ("no", "Not a superior officer")),
            ),
            Field("account", "Record the concrete established rank facts", paragraph=True),
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.rank,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["superior"] == ("yes",),
                values["account"],
            )
            return "Actual relative rank recorded. This is not a declaration of guilt or innocence."
    elif data["kind"] == "enforcer_release_position":
        fields = [
            Field("x", "Actual released NPC map X"),
            Field("y", "Actual released NPC map Y"),
            Field("account", "Source proving the actual current location", paragraph=True),
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.record_released_position,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                (int(values["x"]), int(values["y"])),
                values["account"],
            )
            return "The released original NPC's actual current position is recorded."
    else:
        fields = [
            Field("evidence", "Actual evidence proving this NPC innocent", paragraph=True),
            Field(
                "confirm",
                "Actual sourceful release",
                (("yes", "Innocence is proved; release from Foundation detention"),),
            ),
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.release,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["evidence"],
            )
            return (
                "Innocence evidence recorded and Foundation detention ended. "
                "The NPC's physical location still needs a fresh actual source."
            )

    form = NativeForm(
        viewer.user_id,
        "Actual Enforcer case",
        "Answer as the current Handler using the established fiction. "
        "No private testimony is inferred from a player's other roles.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)
