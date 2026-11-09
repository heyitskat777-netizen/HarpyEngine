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
    from girlframe.discord_adapter.m3_sup import GROW, add_growth, open_choice_growth

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
            add_growth(tuple((x["id"], x["label"]) for x in detail["assets"]), detail),
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
    if detail.get("storage_available"):
        fields.append(
            Field(
                "storage",
                "Optional new Void destination",
                (("yes", "Store in the actual connected Harpy"),),
                minimum=0,
                required=False,
            )
        )
    if detail.get("casualty_parts"):
        fields.extend(
            [
                Field(
                    "casualty_part",
                    "Optional Wounded God: infected part to break",
                    tuple((x["id"], x["name"]) for x in detail["casualty_parts"]),
                    minimum=0,
                    required=False,
                ),
                Field(
                    "casualty_site_account",
                    "Actual infected anatomical site, if resisting",
                    paragraph=True,
                    required=False,
                ),
            ]
        )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        choice = values["total"][0]
        if choice == "pass":
            if (
                values.get("asset")
                or values.get("description", "").strip()
                or values.get("storage")
                or values.get("casualty_part")
                or values.get("casualty_site_account", "").strip()
            ):
                raise WorkflowError("Decline with no Asset or Void alteration selected")
            answer = ChoiceAnswer()
        else:
            if not values.get("asset"):
                raise WorkflowError("Choose the actual Asset that pays for this shift")
            if values["asset"][0] == GROW:
                if values.get("casualty_part") or values.get("casualty_site_account", "").strip():
                    raise WorkflowError("Choose growth or an existing body's resisted onset")
                await open_choice_growth(current, game, identity, data, detail, number=int(choice))
                return None
            answer = ChoiceAnswer(
                number=int(choice),
                fields=dict(asset=values["asset"][0])
                | ({"storage": "yes"} if values.get("storage") else {})
                | (
                    dict(
                        casualty_part=values["casualty_part"][0],
                        casualty_site_account=values.get("casualty_site_account", ""),
                    )
                    if values.get("casualty_part")
                    else {"casualty_site_account": values["casualty_site_account"]}
                    if values.get("casualty_site_account", "").strip()
                    else {}
                ),
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
        + ". A shift costs real Void; raw dice and Tags stay recorded."
        + (
            " Paying spends your one-use lesson. Its Risk Factor protection covers only this "
            "payment's real Void consequence; any required resistance remains owed."
            if detail.get("learned_source")
            else ""
        ),
        fields,
        submit,
    ).present(interaction)
