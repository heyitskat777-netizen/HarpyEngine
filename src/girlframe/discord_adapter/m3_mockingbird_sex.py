"""Owned mechanical responses only; players supply the conversation and actual facts."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError


async def open_sex(interaction: discord.Interaction, game: GameService, identity: str) -> None:
    data = await asyncio.to_thread(game.decision, viewer_from_interaction(interaction), identity)
    detail = data["mockingbird_play"]
    if data["kind"] == "mockingbird_handler_girl_void":
        from girlframe.discord_adapter.m3_handler_girl_void import open_handler_girl_void
        from girlframe.services.m3_handler_girl_void import HandlerGirlVoidService

        await open_handler_girl_void(
            interaction, HandlerGirlVoidService(game.store, game), detail["work_id"]
        )
        return
    if data["kind"] == "mockingbird_handler_void":
        from girlframe.discord_adapter.m3_handler_void import open_handler_void
        from girlframe.services.m3_handler_void import HandlerVoidService

        await open_handler_void(
            interaction, HandlerVoidService(game.store, game), detail["work_id"]
        )
        return
    if data["kind"] == "mockingbird_sex_select":
        from girlframe.discord_adapter.m3_mockingbird_plays import LABELS

        titles = dict(
            collect="Take and redirect Void",
            hide="Teach hiding or suppression",
            starry="Give Starry-Eyed",
        )
        fields = [
            Field(
                "option",
                "Choose your printed effect",
                tuple((x, titles[x]) for x in detail["options"]),
            ),
            Field(
                "capability",
                "Starry-Eyed: choose the conversation capability",
                tuple((x, LABELS[x]) for x in detail["capabilities"]),
                minimum=0,
                required=False,
            ),
        ]
    elif data["kind"] == "mockingbird_sex_high_commit":
        fields = [
            Field(
                "confirm",
                "Apply the printed Void consequence to " + detail["target"] + "?",
                (("yes", "Apply actual source effect"),),
            )
        ]
    else:
        raise WorkflowError("This intimacy response's real source port is still being completed")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            ChoiceAnswer(
                options=(values["option"][0],),
                fields={"capability": values["capability"][0]} if values.get("capability") else {},
            )
            if data["kind"] == "mockingbird_sex_select"
            else ChoiceAnswer(flag=values["confirm"][0] == "yes"),
        )
        return (
            "Mechanical effect saved. Play: "
            + str(result["state"])
            + ". The actual participant chooses their own response."
        )

    await NativeForm(
        interaction.user.id,
        "Your owned mechanical effect",
        "Players supply their own decisions. "
        "Private events do not automatically become Handler knowledge.",
        fields,
        submit,
    ).present(interaction)
