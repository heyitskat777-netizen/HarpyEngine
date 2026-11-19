"""Native purchase-backed Kiss Me, Darling and original human review."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_harpy_kiss import KissService

TITLE = "Kiss Me, Darling"


async def open_kiss(
    interaction: discord.Interaction, service: KissService, channel: int, actor: ActorRef
) -> None:
    data = await asyncio.to_thread(
        service.menu, viewer_from_interaction(interaction), channel, actor
    )
    actions = tuple(data["actions"].items())
    if not actions:
        await reply(interaction, "This Harpy has no eligible original surprise Play to review.")
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.propose,
            viewer_from_interaction(click),
            str(click.id),
            channel,
            actor,
            data["revision"],
            values["action"][0],
            values["choice"][0],
            values["account"],
        )
        return "The original scene facilitator can verify the source in their private Inbox."

    fields = [
        Field("action", "The original qualifying Play", actions),
        Field("choice", "Your response", (("kiss", "Kiss"), ("linger", "Linger close"))),
        Field("account", "What established surprise?", paragraph=True),
    ]
    form = NativeForm(
        interaction.user.id,
        TITLE,
        "Use the advancement with the actual original Play.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_surprise(
    interaction: discord.Interaction, service: KissService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.confirm,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            values["choice"][0] == "yes",
        )
        return "The original surprise review is saved."

    form = NativeForm(
        interaction.user.id,
        TITLE,
        "Verify that the original Play caught "
        + clean(data["girl"])
        + " by surprise.\n"
        + clean(data["account"]),
        [Field("choice", "Your actual ruling", (("yes", "Confirm"), ("no", "Decline")))],
        submit,
    )
    await reply(interaction, form.text(), form)
