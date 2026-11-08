"""Native Modular Build acquisition; actual repair replacement lives in Off-Duty recovery."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_modular import Replacement
from girlframe.services.m3_modular import ModularService
from girlframe.services.onboarding import WorkflowError


def replacement_fields(assets: list[dict[str, str]], maximum: int) -> list[Field]:
    if not assets:
        return []
    result = [
        Field(
            "modular_assets",
            "Optional Modular Build repair replacements",
            tuple((x["id"], x["label"]) for x in assets),
            0,
            min(maximum, len(assets)),
            required=False,
        )
    ]
    for asset in assets:
        result.extend(
            [
                Field(
                    "modular_name:" + asset["id"],
                    "Replacement for " + asset["label"],
                    required=False,
                ),
                Field(
                    "modular_description:" + asset["id"],
                    "Describe replacement for " + asset["label"],
                    paragraph=True,
                    required=False,
                ),
            ]
        )
    return result


def replacements(values: dict[str, Any]) -> tuple[Replacement, ...]:
    return tuple(
        Replacement(
            asset=asset,
            name=values.get("modular_name:" + asset, ""),
            description=values.get("modular_description:" + asset, ""),
        )
        for asset in values.get("modular_assets", ())
    )


async def open_purchase(interaction: discord.Interaction, service: ModularService) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction))
    if not data["available"]:
        raise WorkflowError("No reviewed Modular Build source is available")
    if data["suspended"]:
        await reply(
            interaction, "This Class Requisition is suspended. Restore its original paid source."
        )
        return
    if data["owned"]:
        await reply(
            interaction,
            "Modular Build is acquired: six counted Frame slots. "
            "Actual Off-Duty recovery offers replacement of eligible damaged Frame Assets.",
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
            values["name"],
            values["description"],
            values["donor"][0] if data["donors"] else None,
        )
        return (
            f"Modular Build acquired for {data['price']} Permissions; "
            "your additional Frame Asset is saved."
        )

    await NativeForm(
        interaction.user.id,
        f"Modular Build — {data['kind'].replace('_', ' ').title()}, {data['price']} Permissions",
        "Gain one additional maximum Frame Asset slot and write one actual new Frame Asset. "
        "Free intrinsic Assets remain outside the counted limit.",
        (
            [Field("donor", "Choose the actual donor Frame", tuple((x, x) for x in data["donors"]))]
            if data["donors"]
            else []
        )
        + [
            Field("name", "New Frame Asset name"),
            Field("description", "Describe your new Frame Asset", paragraph=True),
            Field("account", "Record your actual acquisition", paragraph=True),
        ],
        submit,
    ).present(interaction)
