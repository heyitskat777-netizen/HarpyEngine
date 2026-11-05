"""Actual target selectors and owned Initiative responses, resumable from saved decisions."""

import asyncio
from typing import Any
from uuid import uuid4

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_enforcement_initiative import preview
from girlframe.services.onboarding import WorkflowError

LABELS = {
    "escape": "Ask how they slip free",
    "item": "They take an object from you",
    "tag": "Receive their actual chosen Tag",
    "disapproval": "Handler disapproval; lower Status",
    "hesitate": "Hesitate; let them use a weapon on hand",
}


async def open_initiative(interaction: discord.Interaction, game: GameService) -> None:
    viewer = viewer_from_interaction(interaction)
    if interaction.channel_id is None:
        raise WorkflowError("Use the actual joined scene channel.")
    channel = interaction.channel_id
    data = await asyncio.to_thread(preview, game, viewer, channel)
    if not data["available"]:
        raise WorkflowError(
            "No actual source-supported cast target is available for Enforcement Initiative."
        )
    targets = {x["token"]: x for x in data["targets"]}
    fields = [
        Field(
            "target",
            "Actual person you take hold of",
            tuple((k, v["label"]) for k, v in targets.items()),
        ),
        Field(
            "heat", "Spend actual Heat", tuple((str(x), str(x)) for x in range(data["heat"] + 1))
        ),
        Field("context", "Describe actual taking hold and contact", paragraph=True),
    ]
    if data["piloting"] is None:
        fields.append(
            Field(
                "piloting",
                "Actual linked Frame context",
                (("yes", "Piloting"), ("no", "Not piloting")),
            )
        )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        selected = targets[values["target"][0]]
        result = await asyncio.to_thread(
            game.begin,
            viewer_from_interaction(current),
            str(current.id),
            channel,
            data["sheet_revision"],
            PlayInput(
                play="enforcement_initiative",
                trigger_confirmed=True,
                context=values["context"],
                heat=int(values["heat"][0]),
                piloting=data["piloting"]
                if data["piloting"] is not None
                else values["piloting"][0] == "yes",
                target_actor=ActorRef.model_validate(selected["ref"]),
            ),
        )
        return (
            "Actual Initiative prepared: "
            + str(result["action_id"])
            + ". Confirm its roll from Pending decisions."
        )

    await NativeForm(
        viewer.user_id,
        "Enforcement Initiative",
        "Confirm actual contact. Known contradictory positions are rejected; "
        "unknown locations stay unknown.",
        fields,
        submit,
    ).present(interaction)


async def open_enforcer_choice(
    interaction: discord.Interaction, game: GameService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(game.decision, viewer, identity)
    detail = data["enforcement"]
    kind = data["kind"]
    if kind == "enforcer_void_threshold":
        from girlframe.discord_adapter.m3_void import open_void
        from girlframe.services.m3_void import VoidService

        await open_void(interaction, VoidService(game.store), detail["work_id"])
        return
    if kind == "enforcer_punishment":
        from girlframe.discord_adapter.m3_role_punishments import open_role_punishment
        from girlframe.services.m3_role_punishments import RolePunishmentService

        await open_role_punishment(interaction, RolePunishmentService(game), detail["case_id"])
        return
    if kind == "enforcer_handler_consequence":
        from girlframe.discord_adapter.m3_handler_consequences import open_consequence
        from girlframe.services.m3_handler_consequences import HandlerConsequenceService

        await open_consequence(
            interaction, HandlerConsequenceService(game.store), detail["consequence"]
        )
        return
    fields: list[Field] = []
    if kind == "enforcer_select":
        fields.append(
            Field(
                "options",
                "Choose exactly two low outcomes",
                tuple((x, LABELS[x]) for x in detail["options"]),
                minimum=2,
                maximum=2,
            )
        )
    elif kind == "enforcer_item":
        fields.append(
            Field(
                "item",
                "Choose actual held object",
                tuple((x["id"], x["label"]) for x in detail["items"]),
            )
        )
        fields.append(
            Field("account", "Describe taking this object from the Enforcer", paragraph=True)
        )
    elif kind == "enforcer_item_context":
        fields += [
            Field(
                "inside_frame",
                "Your actual physical inside/outside Frame",
                (("yes", "Inside a Frame"), ("no", "Outside a Frame")),
            ),
            Field("account", "Evidence of your actual body context", paragraph=True),
        ]
    elif kind == "enforcer_receive":
        fields.append(
            Field(
                "replace",
                "Replace only if real capacity requires it",
                (
                    ("", "No replacement"),
                    *tuple((x["id"], x["label"]) for x in detail["replacements"]),
                ),
            )
        )
    elif kind == "enforcer_hesitate":
        fields.append(
            Field(
                "accept",
                "Use a weapon on hand?",
                (
                    ("no", "Decline"),
                    *((("yes", "Make the Enforcer Helpless"),) if detail["items"] else ()),
                ),
            )
        )
        if detail["items"]:
            fields.append(
                Field(
                    "weapon",
                    "Actual weapon on hand",
                    tuple((x["id"], x["label"]) for x in detail["items"]),
                )
            )
        fields.append(Field("account", "Describe actual response", paragraph=True))
    else:
        labels = {
            "enforcer_escape": "How do you slip their grip, escaping?",
            "enforcer_tag": "What Tag do you give them?",
            "enforcer_disapproval": "Express actual Handler disapproval",
        }
        if kind not in labels:
            raise WorkflowError("Resume this actual owned source consequence.")
        fields.append(Field("account", labels[kind], paragraph=True))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        answer = ChoiceAnswer(
            options=tuple(values.get("options", ())),
            text=values.get("account", ""),
            fields={
                k: values[k][0]
                for k in ("item", "weapon", "inside_frame", "replace")
                if k in values
            },
            flag=values.get("accept", ("no",))[0] == "yes" if kind == "enforcer_hesitate" else None,
        )
        result = await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id) or str(uuid4()),
            identity,
            data["revision"],
            answer,
        )
        return "Actual owned response saved. Play " + str(result["state"]) + "."

    await NativeForm(
        viewer.user_id,
        "Enforcement Initiative response",
        "The actual source scene stays held until each required effect is complete.",
        fields,
        submit,
    ).present(interaction)


async def open_grasp(interaction: discord.Interaction, game: GameService, identity: str) -> None:
    from girlframe.services.m3_enforcer import EnforcerService

    viewer = viewer_from_interaction(interaction)
    service = EnforcerService(game)
    rows = await asyncio.to_thread(service.grasps, viewer)
    saved = next((x for x in rows if x["id"] == identity and x["held"]), None)
    if saved is None:
        raise WorkflowError(
            "This actual held grasp belongs to another original holder or already ended."
        )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.release_grasp,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            saved["revision"],
            values["account"],
        )
        return (
            "Actual grip released. Positions are unchanged; "
            "separate Helplessness needs its real recovery."
        )

    await NativeForm(
        viewer.user_id,
        "Release your actual grip",
        "Release only your original held grasp. Nobody is moved, "
        "and separate Helplessness is preserved.",
        [Field("account", "Describe your voluntary release", paragraph=True)],
        submit,
    ).present(interaction)
