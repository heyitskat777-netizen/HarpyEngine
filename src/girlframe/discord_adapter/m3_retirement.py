"""Explicit original-owner confirmation of paid Retirement."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_retirement import RetirementService


async def open_retirement(interaction: discord.Interaction, service: RetirementService) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.view, viewer)

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.retire,
            viewer_from_interaction(current),
            str(current.id),
            ActorRef.model_validate(data["actor"]),
            data["source_sha256"],
            values["account"],
            True,
        )
        return (
            "Retirement paid and original career archived. "
            "Surgeries are reversed and she goes home. "
            "A replacement requires its own new draft and activation. Archive: "
            + str(result["archive_id"])
        )

    form = NativeForm(
        viewer.user_id,
        "Retire this Girl",
        "This costs 20 available Permissions and ends your current Girl's Pilot career. "
        "Her original sheet and history remain archived; "
        "a new Girl receives no inherited resources.",
        [
            Field("account", "Describe her actual Retirement", paragraph=True),
            Field(
                "confirm",
                "Your explicit decision",
                (("yes", "Pay 20 Permissions and retire this Girl"),),
            ),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
