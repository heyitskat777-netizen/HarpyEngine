"""Private real Risk Factor decisions, preserving the known roll receipt."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError


async def open_mockingbird(
    interaction: discord.Interaction, game: GameService, identity: str
) -> None:
    data = await asyncio.to_thread(game.decision, viewer_from_interaction(interaction), identity)
    detail = data["mockingbird"]
    if data["kind"] == "mockingbird_void_threshold":
        from girlframe.discord_adapter.m3_void import open_void
        from girlframe.services.m3_void import VoidService

        await open_void(interaction, VoidService(game.store), detail["work_id"])
        return
    fields = [
        Field(
            "total",
            "Risk Factor: choose a result or decline",
            (("pass", "Decline"), ("8", "8"), ("9", "9"), ("10", "10")),
        ),
        Field(
            "asset",
            "For a shift: actual uncorrupted Asset",
            tuple((x["id"], x["label"]) for x in detail["assets"]),
            minimum=0,
            required=False,
        ),
        Field(
            "description",
            "For a shift: describe the Void alteration",
            paragraph=True,
            required=False,
        ),
    ]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        choice = values["total"][0]
        if choice == "pass":
            if values.get("asset") or values.get("description", "").strip():
                raise WorkflowError("Decline with no Asset or Void alteration selected")
            answer = ChoiceAnswer()
        else:
            if not values.get("asset"):
                raise WorkflowError("Choose the actual Asset that pays for this shift")
            answer = ChoiceAnswer(
                number=int(choice),
                fields=dict(asset=values["asset"][0]),
                text=values.get("description", ""),
            )
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            answer,
        )
        return "Risk Factor choice saved. Resume your original Play from pending decisions."

    await NativeForm(
        interaction.user.id,
        "Risk Factor",
        "Current actual total: "
        + str(detail["total"])
        + ". A shift costs real Void; raw dice and Tags stay recorded.",
        fields,
        submit,
    ).present(interaction)
