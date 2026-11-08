"""Owned battlefield maneuvers with actual per-maneuver Asset selections."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.engine.m2 import MANEUVERS, ChoiceAnswer
from girlframe.services.m2_game import GameService


async def open_engage(interaction: discord.Interaction, game: GameService, identity: str) -> None:
    data = await asyncio.to_thread(game.decision, viewer_from_interaction(interaction), identity)
    detail = data["engage"]
    assets = tuple((asset["id"], asset["label"]) for asset in detail["assets"])
    fields = [
        Field(
            "maneuvers",
            "Choose your battlefield maneuvers",
            tuple((kind, kind.replace("_", " ").title()) for kind in MANEUVERS),
            minimum=detail["minimum"],
            maximum=detail["maximum"],
            required=bool(detail["minimum"]),
        ),
        *[
            Field(
                "asset_" + kind,
                "Actual Asset for " + kind.replace("_", " "),
                assets,
                minimum=0,
                required=False,
            )
            for kind in MANEUVERS
        ],
        Field(
            "text",
            "Describe the actual resulting battlefield circumstances",
            paragraph=True,
            required=bool(detail["minimum"]),
        ),
    ]
    if detail["damage"]:
        substitutions = detail.get("untouchable_tags", [])
        fields.append(
            Field(
                "denied",
                "Damage a used Asset (or choose Untouchable Tag)",
                assets,
                minimum=0 if substitutions else 1,
                required=not substitutions,
            )
        )
        if substitutions:
            fields.append(
                Field(
                    "untouchable_tag",
                    "Instead: mark your own Untouchable Tag",
                    tuple((x["id"], x["label"]) for x in substitutions),
                    minimum=0,
                    required=False,
                )
            )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        choices = tuple(values.get("maneuvers", ()))
        selected_fields = {
            kind: values["asset_" + kind][0] for kind in choices if values.get("asset_" + kind)
        }
        if values.get("untouchable_tag"):
            selected_fields["untouchable_tag"] = values["untouchable_tag"][0]
        answer = ChoiceAnswer(
            options=choices,
            fields=selected_fields,
            denied=tuple(values.get("denied", ())),
            text=values.get("text", ""),
        )
        result = await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            answer,
        )
        return "Your actual battlefield response is saved. Play: " + str(result["state"]) + "."

    await NativeForm(
        interaction.user.id,
        "Your battlefield maneuvers",
        "Select an actual owned Asset for every selected maneuver. "
        "Describe circumstances; these choices do not invent movement between map cells.",
        fields,
        submit,
    ).present(interaction)
