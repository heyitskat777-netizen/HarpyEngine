"""Private owned mechanical choices; humans author their own interaction and facts."""

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
    kind = data["kind"]
    if kind in ("mockingbird_handler_girl_void", "mockingbird_redirect_handler_girl_void"):
        from girlframe.discord_adapter.m3_handler_girl_void import open_handler_girl_void
        from girlframe.services.m3_handler_girl_void import HandlerGirlVoidService

        await open_handler_girl_void(
            interaction, HandlerGirlVoidService(game.store, game), detail["work_id"]
        )
        return
    if kind in ("mockingbird_handler_void", "mockingbird_redirect_handler_void"):
        from girlframe.discord_adapter.m3_handler_void import open_handler_void
        from girlframe.services.m3_handler_void import HandlerVoidService

        await open_handler_void(
            interaction, HandlerVoidService(game.store, game), detail["work_id"]
        )
        return
    if kind == "mockingbird_sex_void_threshold":
        from girlframe.discord_adapter.m3_void import open_void
        from girlframe.services.m3_void import VoidService

        await open_void(interaction, VoidService(game.store), detail["work_id"])
        return
    destinations = {}
    if kind == "mockingbird_sex_select":
        from girlframe.discord_adapter.m3_mockingbird_plays import LABELS

        titles = dict(
            collect="Take and redirect actual Void",
            hide="Teach hiding or suppression",
            starry="Give Starry-Eyed",
        )
        fields = [
            Field(
                "option",
                "Choose one printed effect",
                tuple((x, titles[x]) for x in detail["options"]),
            ),
            Field(
                "capability",
                "For Starry-Eyed: conversation capability",
                tuple((x, LABELS[x]) for x in detail["capabilities"]),
                minimum=0,
                required=False,
            ),
        ]
    elif kind == "mockingbird_sex_infect":
        fields = [
            Field(
                "asset",
                "Actual counterpart Asset you choose",
                tuple((x["id"], x["label"]) for x in detail["assets"]),
            )
        ]
    elif kind == "mockingbird_sex_redirect":
        options: list[tuple[str, str]] = []
        for person in detail["destinations"]:
            choices = person["assets"] if not person["self"] else []
            if choices:
                for asset in choices:
                    token = str(len(options))
                    destinations[token] = (person["token"], asset["id"])
                    options.append((token, person["label"] + " — " + asset["label"]))
            else:
                token = str(len(options))
                destinations[token] = (person["token"], "")
                options.append(
                    (
                        token,
                        person["label"]
                        + (
                            " — write my own Void Asset"
                            if person["self"]
                            else " — actual physiological Void"
                        ),
                    )
                )
        fields = [
            Field(
                "source_asset",
                "Actual Void Asset to take from",
                tuple((x["id"], x["label"]) for x in detail["void_assets"]),
            ),
            Field("destination", "Actual source participant / destination", tuple(options)),
        ]
    elif kind == "mockingbird_sex_hide":
        fields = [
            Field(
                "corruption",
                "Actual corruption you hide or suppress",
                tuple((x["id"], x["label"]) for x in detail["corruption"]),
                maximum=max(1, len(detail["corruption"])),
            ),
            Field("account", "Describe your actual suppression; the Void remains", paragraph=True),
        ]
    elif kind in ("mockingbird_sex_restore", "mockingbird_sex_rewrite"):
        fields = [
            Field(
                "description",
                "Describe your actual Asset after Void is taken away"
                if kind == "mockingbird_sex_restore"
                else "Rewrite your actual chosen Asset's Void alteration",
                paragraph=True,
            )
        ]
        if kind == "mockingbird_sex_rewrite" and detail.get("storage_available"):
            fields.append(
                Field(
                    "storage",
                    "Optional gained Void destination",
                    (("yes", "Store in my actual connected Harpy"),),
                    minimum=0,
                    required=False,
                )
            )
    elif kind == "mockingbird_sex_self":
        fields = [
            Field("name", "Name the actual new Void Asset"),
            Field("description", "Describe the Void taken into yourself", paragraph=True),
        ]
        if detail.get("storage_available"):
            fields.append(
                Field(
                    "storage",
                    "Optional gained Void destination",
                    (("yes", "Store in my actual connected Harpy"),),
                    minimum=0,
                    required=False,
                )
            )
        if detail["replacement_required"]:
            if not detail["replace"]:
                raise WorkflowError(
                    "No actual non-Void Girl Asset can be replaced at your cap; "
                    "revise the uncommitted destination"
                )
            fields.append(
                Field(
                    "replace",
                    "Actual ordinary non-Void Girl Asset to replace",
                    tuple((x["id"], x["label"]) for x in detail["replace"]),
                )
            )
    elif kind in ("mockingbird_sex_npc_void", "mockingbird_sex_redirect_npc"):
        fields = [
            Field(
                "manifestation",
                "Actual NPC Void manifestation",
                tuple((x, x.title()) for x in ("brain", "bones", "flesh", "abstract")),
            )
        ]
    elif kind == "mockingbird_sex_high_commit":
        fields = [
            Field(
                "confirm",
                "Apply the printed physiological consequence to " + detail["target"] + "?",
                (("yes", "Commit actual source effect"),),
            )
        ]
    else:
        raise WorkflowError("Use this exact owned intimacy response")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if kind == "mockingbird_sex_select":
            answer = ChoiceAnswer(
                options=(values["option"][0],),
                fields={"capability": values["capability"][0]} if values.get("capability") else {},
            )
        elif kind == "mockingbird_sex_infect":
            answer = ChoiceAnswer(fields={"asset": values["asset"][0]})
        elif kind == "mockingbird_sex_redirect":
            destination, asset = destinations[values["destination"][0]]
            answer = ChoiceAnswer(
                fields=dict(
                    source_asset=values["source_asset"][0],
                    destination=destination,
                    destination_asset=asset,
                )
            )
        elif kind == "mockingbird_sex_hide":
            answer = ChoiceAnswer(options=tuple(values["corruption"]), text=values["account"])
        elif kind in ("mockingbird_sex_restore", "mockingbird_sex_rewrite"):
            answer = ChoiceAnswer(
                text=values["description"],
                fields={"storage": "yes"} if values.get("storage") else {},
            )
        elif kind == "mockingbird_sex_self":
            answer = ChoiceAnswer(
                fields={
                    "name": values["name"],
                    "replace": values["replace"][0] if values.get("replace") else "",
                }
                | ({"storage": "yes"} if values.get("storage") else {}),
                text=values["description"],
            )
        elif kind in ("mockingbird_sex_npc_void", "mockingbird_sex_redirect_npc"):
            answer = ChoiceAnswer(fields={"manifestation": values["manifestation"][0]})
        else:
            answer = ChoiceAnswer(flag=values["confirm"][0] == "yes")
        result = await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            answer,
        )
        return "Your actual mechanical response is saved. Play: " + str(result["state"]) + "."

    await NativeForm(
        interaction.user.id,
        "Your owned mechanical effect",
        "Only the actual owner supplies their choices/descriptions. "
        "Private events do not automatically become Handler knowledge. "
        "This source uses one original receipt and no generated fictional acts.",
        fields,
        submit,
    ).present(interaction)
