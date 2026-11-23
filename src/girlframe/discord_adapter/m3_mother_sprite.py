"""Private review of real Sprite movement and the selected adult Class."""

import asyncio
from typing import Any, Literal, cast

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_mother_sprite import Adult
from girlframe.services.m3_mother_sprite import SpriteEscapeService


async def open_review(interaction: discord.Interaction, service: SpriteEscapeService) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.options, viewer)
    if not data["options"]:
        await reply(interaction, "No original Sprite movement awaits an escape ruling.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        choice = values["result"][0]
        adult = (
            Adult(
                gorgon_class=cast(Literal["benevolent", "dormant", "erratic"], choice),
                extra_assets=tuple(
                    x.strip() for x in values.get("assets", "").splitlines() if x.strip()
                ),
            )
            if choice != "stayed"
            else None
        )
        await asyncio.to_thread(
            service.review,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            values["movement"][0],
            values["account"],
            adult,
        )
        return (
            "The original Sprite is due to mature at the next Off-Duty activation."
            if adult
            else "The original Sprite did not escape in this movement."
        )

    form = NativeForm(
        viewer.user_id,
        "Review a Sprite escape",
        "Review the actual movement. Keep its original body, Core and Asset. "
        "For an escape, name the additional Assets for the selected adult Class.",
        [
            Field(
                "movement",
                "Actual Sprite movement",
                tuple(
                    (source, f"{label} · {origin} to {destination}")
                    for source, label, origin, destination in data["options"]
                ),
            ),
            Field(
                "result",
                "Actual table ruling",
                (
                    ("stayed", "The Sprite did not escape"),
                    ("benevolent", "Escaped · Benevolent, add one Asset"),
                    ("dormant", "Escaped · Dormant, add two Assets"),
                    ("erratic", "Escaped · Erratic, add three Assets"),
                ),
            ),
            Field("assets", "Added Assets, one per line", required=False, paragraph=True),
            Field("account", "Explain what happened in the scene", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
