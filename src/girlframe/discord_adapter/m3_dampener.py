"""Optional source-owned Dampener preparation and native acquisition."""

import asyncio
from typing import Any, Literal, cast

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_dampener import DampenerService
from girlframe.services.onboarding import WorkflowError


async def fields(
    interaction: discord.Interaction, service: DampenerService, actor: ActorRef | None = None
) -> list[Field]:
    if actor is not None and actor.kind != "pilot":
        return []
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), actor)
    if not data["available"] or not data["owned"]:
        return []
    return [
        Field(
            "dampener_modifier",
            "When spending at least 5 Heat: Dampener basis",
            (
                ("normal", "Use full Heat spent"),
                ("2", "Use +2; still spend all selected Heat"),
                ("3", "Use +3; still spend all selected Heat"),
            ),
            minimum=0,
            required=False,
        )
    ]


def modifier(values: dict[str, Any]) -> Literal[2, 3] | None:
    selected = values.get("dampener_modifier", ())
    return cast(Literal[2, 3], int(selected[0])) if selected and selected[0] != "normal" else None


async def open_purchase(interaction: discord.Interaction, service: DampenerService) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction))
    if not data["available"]:
        raise WorkflowError("No reviewed native LEGION Dampener acquisition is available")
    if data["owned"]:
        await reply(
            interaction,
            "Dampener Link is acquired. You control your facial expressions. "
            "When spending at least five Heat, you may use +2 or +3 while still paying that Heat.",
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.buy,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            ActorRef.model_validate(data["actor"]),
            data["frame"],
            values["account"],
        )
        return "Dampener Link acquired for two Permissions. Choose its basis in Heat preparation."

    await NativeForm(
        interaction.user.id,
        "Dampener Link — native LEGION, 2 Permissions",
        "Control your facial expressions. Spend at least five Heat to choose a +2 or +3 basis.",
        [Field("account", "Record your actual acquisition", paragraph=True)],
        submit,
    ).present(interaction)
