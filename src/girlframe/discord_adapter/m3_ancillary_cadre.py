"""Native formation and independent role acceptance for an optional Cadre."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_ancillary_cadre import AncillaryCadreService

TITLE = "Ancillary Cadre"


async def open_ancillary_cadre(
    interaction: discord.Interaction,
    service: AncillaryCadreService,
    channel: int,
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), channel)
    people = tuple(data["people"].items())
    fields = [Field("handler", "Original Handler", tuple(data["handlers"].items()))]
    fields.extend(
        Field(
            "rank" + str(i), "Status position " + str(i), people, 0 if i > 2 else 1, required=i <= 2
        )
        for i in range(1, min(4, len(people)) + 1)
    )

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        slots = [values.get("rank" + str(i), ()) for i in range(1, 5)]
        order = tuple(slot[0] for slot in slots if slot)
        await asyncio.to_thread(
            service.propose,
            viewer_from_interaction(click),
            str(click.id),
            channel,
            data["revision"],
            values["handler"][0],
            order,
        )
        return "The original proposed members have private invitations."

    form = NativeForm(
        interaction.user.id,
        TITLE,
        "Propose an original group in Status order, highest first.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_cadre_invitation(
    interaction: discord.Interaction,
    service: AncillaryCadreService,
    identity: str,
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    text = "Proposed Handler — " + clean(data["handler"])
    for index, label in enumerate(data["order"], 1):
        text += f"\n{index}. " + clean(label)

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.approve,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            values["role"][0],
            values["choice"][0] == "yes",
        )
        return "Your original Cadre decision is saved."

    form = NativeForm(
        interaction.user.id,
        TITLE,
        text,
        [
            Field("role", "Your actual role", tuple(data["choices"].items())),
            Field(
                "choice", "Your decision", (("yes", "Accept and share my role"), ("no", "Decline"))
            ),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
