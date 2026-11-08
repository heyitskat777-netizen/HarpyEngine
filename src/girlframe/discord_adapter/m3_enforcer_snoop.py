"""Owned Snoop questions, private original-target answers and actual source facts."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError


async def open_snoop(interaction: discord.Interaction, game: GameService, identity: str) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(game.decision, viewer, identity)
    detail = data["snoop"]
    kind = data["kind"]
    selected: dict[str, tuple[str, str]] = {}
    if kind == "snoop_select":
        fields = [
            Field(
                "questions",
                "Printed Snoop questions",
                tuple((x["id"], x["label"]) for x in detail["questions"]),
                maximum=detail["maximum"],
            )
        ]
    elif kind == "snoop_answer":
        fields = [Field("answer", "Your actual private finding", paragraph=True)]
        if detail["question"] in ("valuable", "personal"):
            options = [("ordinary", "A preexisting ordinary object; give details next")]
            for item in detail["items"]:
                token = str(len(selected))
                selected[token] = ("item", item["id"])
                options.append((token, item["label"]))
            if detail["question"] == "personal":
                for asset in detail["assets"]:
                    token = str(len(selected))
                    selected[token] = ("asset", asset["id"])
                    options.append((token, asset["label"] + " (actual Asset)"))
            fields.extend(
                [
                    Field("object", "Identify actual property", tuple(options)),
                    Field("name", "Ordinary object's name, if needed", required=False),
                    Field(
                        "description",
                        "Ordinary object and source-room location, if needed",
                        paragraph=True,
                        required=False,
                    ),
                ]
            )
    elif kind == "snoop_object_fact":
        fields = [
            Field(
                "confirm",
                "Does the actual ordinary object exist here?",
                (
                    ("yes", "Actual source existence/access confirmed"),
                    ("no", "Finding needs source correction"),
                ),
            ),
            Field("account", "Actual existence, location and access facts", paragraph=True),
        ]
    elif kind == "snoop_relevance":
        fields = [Field("account", "Actual remaining property and relevant Assets", paragraph=True)]
        if detail["assets"]:
            fields.insert(
                0,
                Field(
                    "assets",
                    "All relevant actual Assets",
                    tuple((x["id"], x["label"]) for x in detail["assets"]),
                    minimum=0,
                    maximum=len(detail["assets"]),
                ),
            )
    elif kind == "snoop_body_context":
        fields = [
            Field(
                "inside",
                "Your actual body's current cockpit context",
                (("yes", "Inside a Frame"), ("no", "Outside a Frame")),
            ),
            Field("account", "Actual body facts; no movement is performed", paragraph=True),
        ]
    elif kind == "snoop_capacity":
        options = [("none", "No inventory replacement needed")] + [
            (x["id"], x["label"]) for x in detail["replacements"]
        ]
        fields = [
            Field("replace", "Replace an actual ordinary Asset only if at cap", tuple(options))
        ]
    elif kind in ("snoop_damage_consequence", "snoop_item_void_threshold"):
        work = data["body"]["work_id"]
        if kind == "snoop_item_void_threshold":
            from girlframe.discord_adapter.m3_void import open_void
            from girlframe.services.m3_void import VoidService

            await open_void(interaction, VoidService(game.store), work)
        else:
            requirement = data["body"]["requirement"]
            if requirement["kind"] == "defeat":
                from girlframe.discord_adapter.m3_defeat import open_work

                await open_work(interaction, game, work)
            elif requirement["kind"] in ("director_damage", "director_helpless"):
                from girlframe.discord_adapter.m3_battle_director import open_director
                from girlframe.services.m3_battle_director import DirectorService

                await open_director(interaction, DirectorService(game.store), work)
            elif requirement["kind"] == "handler_damage":
                from girlframe.discord_adapter.m3_handler_consequences import open_consequence
                from girlframe.services.m3_handler_consequences import HandlerConsequenceService

                await open_consequence(
                    interaction,
                    HandlerConsequenceService(game.store),
                    requirement["details"]["consequence"],
                )
            elif requirement["kind"] == "npc_damage":
                from girlframe.discord_adapter.m3_battle import open_npc_damage
                from girlframe.services.m3_battle_npc import NpcDamageService

                await open_npc_damage(interaction, NpcDamageService(game.store), work)
            else:
                raise WorkflowError("Open this actual required consequence in your requests inbox.")
        return
    else:
        raise WorkflowError("Open the actual saved Snoop choice.")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if kind == "snoop_select":
            answer = ChoiceAnswer(options=tuple(values["questions"]))
        elif kind == "snoop_answer":
            source: dict[str, str] = {}
            if "object" in values:
                value = values["object"][0]
                if value == "ordinary":
                    source = dict(name=values["name"], description=values["description"])
                elif value in selected:
                    key, item = selected[value]
                    source[key] = item
                else:
                    raise WorkflowError("Reopen the actual current source-property choices.")
            answer = ChoiceAnswer(text=values["answer"], fields=source)
        elif kind == "snoop_relevance":
            answer = ChoiceAnswer(options=tuple(values.get("assets", ())), text=values["account"])
        elif kind == "snoop_capacity":
            value = values["replace"][0]
            answer = ChoiceAnswer(fields=dict(replace=value) if value != "none" else {})
        else:
            answer = ChoiceAnswer(
                flag=values["inside" if kind == "snoop_body_context" else "confirm"][0] == "yes",
                text=values["account"],
            )
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            answer,
        )
        return "Your actual Snoop response is saved. Required physical consequences stay pending."

    text = "Private findings do not give an absent body scene knowledge or move its possessions."
    if detail.get("question"):
        from girlframe.engine.m3_enforcer_snoop import LABELS

        text += "\n" + LABELS[detail["question"]]
    form = NativeForm(viewer.user_id, "Snoop", text, fields, submit)
    await reply(interaction, form.text(), form)
