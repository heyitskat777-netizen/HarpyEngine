"""One actual native Class purchase, reviewed privately before the two-Permission payment."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_sup import SupService
from girlframe.services.onboarding import WorkflowError

GROW = "sup_grow"


def add_growth(
    assets: tuple[tuple[str, str], ...], detail: dict[str, Any]
) -> tuple[tuple[str, str], ...]:
    return assets + ((GROW, "Sup: grow a NEW already-Void Asset"),) if detail.get("sup") else assets


async def open_growth(
    interaction: discord.Interaction,
    detail: dict[str, Any],
    submit: Callable[[discord.Interaction, dict[str, str], str], Awaitable[str]],
) -> None:
    source = detail["sup"]

    async def grow(current: discord.Interaction, values: dict[str, Any]) -> str:
        return await submit(
            current,
            dict(
                sup_name=values["name"],
                sup_family=values["family"][0],
                sup_replace="" if values["replace"][0] == "none" else values["replace"][0],
            ),
            values["description"],
        )

    form = NativeForm(
        interaction.user.id,
        "Sup: actual new Void Asset",
        "Grow a new already-Void Asset for this actual gain. Choose a same-family non-Void "
        "replacement only when the normal cap requires it. This is permanent Void, with real "
        "whole-family consequences; it is separate from JANUS Void Storage.",
        [
            Field(
                "family",
                "Actual new Asset family",
                tuple((x, x.title()) for x in source["families"]),
            ),
            Field("name", "Name your NEW Asset"),
            Field("description", "Describe its actual Void corruption", paragraph=True),
            Field(
                "replace",
                "Only at cap: replace actual non-Void Asset",
                (("none", "No replacement; there is room"),)
                + tuple(
                    (x["id"], x["label"] + " · " + x["family"]) for x in source["replacements"]
                ),
            ),
        ],
        grow,
    )
    await form.present(interaction)


async def open_choice_growth(
    interaction: discord.Interaction,
    game: GameService,
    identity: str,
    data: dict[str, Any],
    detail: dict[str, Any],
    *,
    number: int | None = None,
) -> None:
    async def submit(current: discord.Interaction, fields: dict[str, str], text: str) -> str:
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            ChoiceAnswer(fields=fields, text=text, number=number),
        )
        return (
            "Actual Sup growth saved; continue the original source and any real Void consequence."
        )

    await open_growth(interaction, detail, submit)


async def open_purchase(interaction: discord.Interaction, service: SupService) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction))
    if not data["available"]:
        raise WorkflowError("No reviewed Sup acquisition is available")
    if data["suspended"]:
        await reply(
            interaction, "This Class Requisition is suspended. Restore its original paid source."
        )
        return
    if data["owned"]:
        await reply(
            interaction,
            "Sup of Primordial Flesh is acquired for your current Frame. "
            "On actual Void gain, choose to grow a new already-Void Asset.",
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
            values["donor"][0] if data["donors"] else None,
        )
        return (
            f"Sup of Primordial Flesh acquired for {data['price']} Permissions."
            " Choose new Asset growth on your actual Void-gain request."
        )

    await NativeForm(
        interaction.user.id,
        f"Sup of Primordial Flesh — {data['kind'].replace('_', ' ').title()}, "
        f"{data['price']} Permissions",
        "Source-owned Class Requisition. On actual Void gain, grow a new already-Void Asset "
        "instead of rewriting an existing Asset. Normal Asset caps still apply.",
        (
            [Field("donor", "Choose the actual donor Frame", tuple((x, x) for x in data["donors"]))]
            if data["donors"]
            else []
        )
        + [Field("account", "Record the actual acquisition", paragraph=True)],
        submit,
    ).present(interaction)
