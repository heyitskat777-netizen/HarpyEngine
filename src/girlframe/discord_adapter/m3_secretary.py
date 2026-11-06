"""Owned Secretary acquisition, actual four-Play controls and gunpoint responses."""

import asyncio
import json
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_missions import Mission
from girlframe.services.m3_secretary import SecretaryService
from girlframe.services.onboarding import WorkflowError


async def open_gunpoint(
    interaction: discord.Interaction, service: SecretaryService, choice_id: str
) -> None:
    data = await asyncio.to_thread(
        service.game.decision, viewer_from_interaction(interaction), choice_id
    )
    if data["kind"] == "secretary_response_play":
        from girlframe.discord_adapter.m2_ui import open_play

        await open_play(interaction, service.game, parent=data)
        return
    value = data["secretary"]
    options = (
        ("withdraw", "Back down: withdraw this original unrolled action"),
        ("respond", "Make an actual response under gunpoint"),
    )
    if data["kind"] == "secretary_gunpoint_resolution":
        options = (
            ("proceed", "Actual completed response permits the original continuation"),
            ("release", "The Secretary actually lowers its gun"),
        )

    async def answer(current: discord.Interaction, fields: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.game.respond,
            viewer_from_interaction(current),
            str(current.id),
            choice_id,
            data["revision"],
            ChoiceAnswer(options=fields["response"], text=fields["account"]),
        )
        return (
            "Actual source response saved. Reopen the pending Play to continue the owned next step."
        )

    await NativeForm(
        interaction.user.id,
        "Actual Secretary gunpoint response",
        "The actual Secretary holds this original go-after action at gunpoint. "
        "Withdraw to cancel it, or play a response before continuing. "
        "No shot, damage or Helplessness is automatic. Source: " + value["id"],
        [
            Field("response", "Actual tactical choice", options),
            Field("account", "Actual action, response or source resolution", paragraph=True),
        ],
        answer,
    ).present(interaction)


async def open_secretary(
    interaction: discord.Interaction, service: SecretaryService, identity: str | None = None
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), identity)
    if data["kind"] == "performed":
        body = data["body"]
        text = "Actual Secretary work: " + body["play"] + ".\n" + clean(body["account"])
        if body["mission_json"]:
            mission = Mission.model_validate_json(body["mission_json"])
            text += "\nVerified mission objective: " + clean(mission.objective)
            text += "\nActual source mission: " + mission.id
        await reply(interaction, text)
        return
    if data["acquisition"] is None:
        if not data["awards"]:
            await reply(interaction, "One actual held advancement is needed to acquire Secretary.")
            return

        async def buy(current: discord.Interaction, fields: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.buy,
                viewer_from_interaction(current),
                str(current.id),
                fields["award"][0],
                data["revision"],
                fields["account"],
            )
            return "Secretary acquired once. Its History card opens actual promotion or creation."

        await NativeForm(
            interaction.user.id,
            "Acquire Secretary",
            "Spend one held advancement for this original Handler's personal Secretary.",
            [
                Field(
                    "award",
                    "Actual held award",
                    tuple((x["id"], clean(x["label"])[:100]) for x in data["awards"]),
                ),
                Field("account", "Actual acquisition", paragraph=True),
            ],
            buy,
        ).present(interaction)
        return
    if data["secretary"] is None:

        async def appoint(current: discord.Interaction, fields: dict[str, Any]) -> str:
            existing = None
            cell = None
            if fields["branch"][0] == "promote":
                if not fields.get("npc"):
                    raise WorkflowError("Choose the actual existing NPC being promoted")
                existing = fields["npc"][0]
            else:
                if not fields.get("place"):
                    raise WorkflowError("Choose the new person's actual initial place")
                cell = tuple(
                    next(x["cell"] for x in data["places"] if x["id"] == fields["place"][0])
                )
            await asyncio.to_thread(
                service.appoint,
                viewer_from_interaction(current),
                str(current.id),
                data["acquisition"],
                data["revision"],
                fields["style"][0],
                existing=existing,
                name=fields.get("name", ""),
                detail=fields.get("detail", ""),
                cell=cell,
            )
            return "Personal Secretary appointed; its identity and controller are preserved."

        await NativeForm(
            interaction.user.id,
            "Appoint your actual Secretary",
            "Promote an actual NPC or create a new ordinary person. Style describes this person; "
            "it creates no separate AM, clone, weapon Asset or player-character sheet.",
            [
                Field(
                    "branch",
                    "Actual appointment branch",
                    (("promote", "Promote an existing NPC"), ("create", "Create a new Secretary")),
                ),
                Field(
                    "style",
                    "Secretary description",
                    (
                        ("am", "AM"),
                        ("military", "Military"),
                        ("clone", "Clone"),
                        ("competent", "Competent"),
                    ),
                ),
                Field(
                    "npc",
                    "Existing NPC for promotion",
                    tuple((x["id"], x["name"]) for x in data["npcs"]),
                    0,
                    1,
                    required=False,
                ),
                Field("name", "New person's name (creation only)", required=False),
                Field("detail", "New person's actual description", paragraph=True, required=False),
                Field(
                    "place",
                    "New person's actual initial place",
                    tuple((x["id"], x["name"]) for x in data["places"]),
                    0,
                    1,
                    required=False,
                ),
            ],
            appoint,
        ).present(interaction)
        return
    value = data["secretary"]
    npc = json.loads(value["original_npc_json"])
    scenes = tuple(
        (str(x["channel"]), "Scene in channel " + str(x["channel"])) for x in data["scenes"]
    )

    async def choose(current: discord.Interaction, fields: dict[str, Any]) -> str | None:
        selected = fields["play"][0]
        if selected == "appear":

            async def appear(next_step: discord.Interaction, answers: dict[str, Any]) -> str:
                place = next(x for x in data["places"] if x["id"] == answers["place"][0])
                await asyncio.to_thread(
                    service.appear,
                    viewer_from_interaction(next_step),
                    str(next_step.id),
                    value["id"],
                    data["revision"],
                    int(answers["scene"][0]),
                    tuple(place["cell"]),
                    answers["account"],
                )
                return "The actual Secretary appears in the needed place and source cast."

            await NativeForm(
                current.user.id,
                "Secretary — appear where needed",
                "The free Secretary appears at the chosen place and joins the scene.",
                [
                    Field("scene", "Actual needed scene", scenes),
                    Field(
                        "place",
                        "Actual needed place",
                        tuple((x["id"], x["name"]) for x in data["places"]),
                    ),
                    Field("account", "Actual need and appearance", paragraph=True),
                ],
                appear,
            ).present(current)
        elif selected == "authority":
            girls = {
                x["ref"]["entity"]: x["label"] for scene in data["scenes"] for x in scene["girls"]
            }

            async def speak(next_step: discord.Interaction, answers: dict[str, Any]) -> str:
                target = None if answers["target"][0] == "statement" else int(answers["target"][0])
                await asyncio.to_thread(
                    service.speak,
                    viewer_from_interaction(next_step),
                    str(next_step.id),
                    value["id"],
                    data["revision"],
                    int(answers["scene"][0]),
                    answers["text"],
                    target,
                )
                return "The actual Secretary speaks with its original Handler's authority."

            await NativeForm(
                current.user.id,
                "Secretary — full authority",
                "The Secretary speaks; direct Orders use the recipient's normal responses.",
                [
                    Field("scene", "Actual speaking scene", scenes),
                    Field(
                        "target",
                        "Actual speech/Order",
                        (("statement", "An actual authoritative statement"),)
                        + tuple(girls.items()),
                    ),
                    Field("text", "Actual statement or direct Order", paragraph=True),
                ],
                speak,
            ).present(current)
        elif selected == "competence":
            if not data["missions"]:
                raise WorkflowError(
                    "A genuine existing mission supplies this factual dossier's information"
                )

            async def competence(next_step: discord.Interaction, answers: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.competence,
                    viewer_from_interaction(next_step),
                    str(next_step.id),
                    value["id"],
                    data["revision"],
                    answers["mission"][0],
                    answers["account"],
                )
                return "Verified mission briefing delivered to its original recipients' History."

            await NativeForm(
                current.user.id,
                "Secretary — unflinching competence",
                "Deliver a factual briefing. Other competent work remains "
                "normal Conversation; this grants no automatic mission success or resource effect.",
                [
                    Field(
                        "mission",
                        "Actual source mission",
                        tuple((x["id"], clean(x["label"])[:100]) for x in data["missions"]),
                    ),
                    Field("account", "Substantive work and delivered briefing", paragraph=True),
                ],
                competence,
            ).present(current)
        else:
            opportunities = data["opportunities"]
            if not opportunities:
                raise WorkflowError(
                    "No actual original unrolled go-after action is currently in firearm reach"
                )
            weapons = {x["id"]: x["label"] for o in opportunities for x in o["weapons"]}

            async def hold(next_step: discord.Interaction, answers: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.hold,
                    viewer_from_interaction(next_step),
                    str(next_step.id),
                    answers["action"][0],
                    data["revision"],
                    answers["weapon"][0],
                    answers["account"],
                    firearm=answers["firearm"] == ("firearm",),
                )
                return "Unrolled action held at gunpoint. Its original attacker owns the response."

            await NativeForm(
                current.user.id,
                "Secretary — hold at gunpoint",
                "Invoke while the hostile action is unrolled. A carried gun may "
                "be recorded through item controls; no weapon Asset purchase is required.",
                [
                    Field(
                        "action",
                        "Actual original go-after action",
                        tuple((x["action"], x["action"]) for x in opportunities),
                    ),
                    Field("weapon", "Actual carried firearm", tuple(weapons.items())),
                    Field(
                        "firearm",
                        "Actual firearm fact",
                        (("firearm", "This is an actual carried firearm"),),
                    ),
                    Field("account", "Actual gunpoint intervention", paragraph=True),
                ],
                hold,
            ).present(current)
        return None

    await NativeForm(
        interaction.user.id,
        "Personal Secretary — " + clean(npc["name"]),
        "Make these four Handler Plays through this actual person. Ordinary NPC control stays with "
        "its actual controller.",
        [
            Field(
                "play",
                "Actual Secretary Play",
                (
                    ("authority", "Speak with full authority"),
                    ("gunpoint", "Hold a would-be attacker at gunpoint"),
                    ("appear", "Appear where most needed"),
                    ("competence", "Demonstrate unflinching competence"),
                ),
            )
        ],
        choose,
    ).present(interaction)
