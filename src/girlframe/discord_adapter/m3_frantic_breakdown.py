"""Native controls for the original Frantic and each printed outcome chooser."""

import asyncio
from typing import Any, cast

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_frantic_breakdown import Option
from girlframe.services.m3_frantic_breakdown import FranticBreakdownService
from girlframe.services.onboarding import WorkflowError


async def open_start(
    interaction: discord.Interaction, service: FranticBreakdownService, revision: int, channel: int
) -> None:
    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.start,
            viewer_from_interaction(current),
            str(current.id),
            revision,
            channel,
            values["account"],
        )
        return "Break Down rolled " + str(result["total"]) + ". Continue through the private Inbox."

    form = NativeForm(
        viewer_from_interaction(interaction).user_id,
        "Break Down",
        "Roll once with the actual number of operational bases under your responsibility.",
        [Field("account", "Your actual breakdown", paragraph=True)],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_breakdown(
    interaction: discord.Interaction, service: FranticBreakdownService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    instructions = (
        "Saved roll "
        + " + ".join(str(x) for x in data["faces"])
        + " plus "
        + str(data["bases"])
        + " bases, total "
        + str(data["total"])
        + ".\n"
        + clean(data["account"])
    )
    if data["choose"]:
        fixed = {x["token"]: x for x in data["targets"]}
        targets = tuple((key, x["name"]) for key, x in fixed.items())
        count = data["choose"]
        if len(data["options"]) < count:
            raise WorkflowError("This result still needs an unsupported printed effect")
        fields = [
            Field("options", "Choose the actual effects", data["options"], count, count),
        ]
        if "office" in dict(data["options"]):
            fields.append(
                Field("office", "Original Girl for the office scene", targets, required=False)
            )
        if "moderate_one" in dict(data["options"]):
            fields.append(
                Field("moderate", "Original Girl for Moderate Punishment", targets, required=False)
            )

        def original(values: dict[str, Any], key: str) -> ActorRef | None:
            selected = values.get(key)
            return ActorRef.model_validate(fixed[selected[0]]["ref"]) if selected else None

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.select,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                cast(tuple[Option, ...], values["options"]),
                office=original(values, "office"),
                moderate=original(values, "moderate"),
            )
            return "Choices saved. The actual consequences are tracked in their own Inbox items."
    elif data["discover"]:
        fields = [Field("account", "Your actual office discovery", paragraph=True)]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.discover,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["account"],
            )
            return "Your actual discovery has been recorded."
    else:
        await reply(interaction, instructions + "\nCurrent stage " + str(data["phase"]) + ".")
        return
    form = NativeForm(viewer.user_id, "Break Down", instructions, fields, submit)
    await reply(interaction, form.text(), form)
