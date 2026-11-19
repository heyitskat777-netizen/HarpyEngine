"""Owned native Successor advancement and original Gold Star controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_strain_effects import WAIT, DependentForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_successor import SuccessorService


async def open_purchase(
    interaction: discord.Interaction, service: SuccessorService, award: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.advancement.view, viewer, award)

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.buy,
            viewer_from_interaction(current),
            str(current.id),
            award,
            data["revision"],
            values["account"],
        )
        return (
            "Successor acquired. Give advice through Handler Plays and award Stars in your Inbox."
        )

    await NativeForm(
        viewer.user_id,
        "Successor",
        "Spend this actual held advancement.",
        [Field("account", "Why you are preparing a Successor", paragraph=True)],
        submit,
    ).present(interaction)


async def open_successor(
    interaction: discord.Interaction, service: SuccessorService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.menu, viewer, identity)
    options = tuple(
        option
        for option, available in (
            (("award", "Award a Gold Star for an observed lesson"), data["advice"]),
            (("remove", "Remove an actual Gold Star"), data["stars"]),
        )
        if available
    )
    if not options:
        await reply(
            interaction,
            "Give advice in the actual scene. A Girl's later Play can show what she learned.",
        )
        return

    def fields(values: dict[str, Any]) -> list[Field]:
        result = [Field("operation", "Gold Star decision", options)]
        operation = values.get("operation", (None,))[0]
        if operation == "award":
            grant = values.get("advice", (None,))[0]
            result += [
                Field("advice", "Original advice", data["advice"]),
                Field("lesson", "Later performed Play", data["lessons"].get(grant) or WAIT),
                Field("account", "What you observed in the actual Play", paragraph=True),
            ]
        elif operation == "remove":
            result.append(Field("star", "Actual Gold Star", data["stars"]))
        return result

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if values["operation"] == ("award",):
            await asyncio.to_thread(
                service.judge,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["advice"][0],
                values["lesson"][0],
                values["account"],
            )
            return "Gold Star awarded for the actual lesson."
        await asyncio.to_thread(
            service.remove,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["star"][0],
        )
        return "The original Gold Star was removed."

    await DependentForm(
        viewer.user_id,
        "Successor Gold Stars",
        "Choose an actual observed lesson or remove an existing Star.",
        fields,
        submit,
    ).present(interaction)
