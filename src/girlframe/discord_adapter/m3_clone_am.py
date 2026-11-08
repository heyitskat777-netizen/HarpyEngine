"""Private actual Clone AM resources and normal source-owned play controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m2_ui import YES, entities, menu, text
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import FLIRT_QUESTIONS, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_actor_plays import ActorPlayService
from girlframe.services.m3_clone_am import CloneService
from girlframe.services.onboarding import WorkflowError


def flags(label: str, required: bool = True) -> Field:
    return Field("flag", label, YES, required=required)


def choice_fields(decision: dict[str, Any]) -> list[Field]:
    kind, result, data = decision["kind"], decision["result"], decision["clone_flirt"]
    marked = [x for x in data["identities"] if x["marked"]]
    unmark = (
        entities(
            "denied",
            "Actual marked Identities to unmark",
            marked,
            0,
            min(data["maximum"], len(marked)),
            False,
        )
        if marked
        else None
    )
    if kind == "clone_flirt_actor":
        fields = [menu("options", "Ask one printed question", FLIRT_QUESTIONS)]
        if unmark:
            fields.append(unmark)
        if result["tier"] == "high":
            fields += [
                menu("fields.extra", "How do you go too far?", ("escape", "handler", "owe")),
                text("text", "Describe going too far"),
            ]
        return fields
    if kind == "clone_flirt_target":
        fields = [
            text(
                "text",
                "Answer her actual question"
                if result["tier"] != "low"
                else "What pushes you away?",
            )
        ]
        if unmark:
            fields.append(unmark)
        if result["tier"] == "low":
            fields.append(menu("options", "Optional return question", FLIRT_QUESTIONS, 0, 1, False))
        if result.get("question") == "intimacy":
            fields.append(flags("My actual consent", False))
        return fields
    if kind == "clone_flirt_answer":
        return [text("text", "Answer her actual return question")]
    if kind == "clone_flirt_followthrough_confirm":
        return [
            flags("Did the actual described follow-through happen?"),
            text("text", "Confirm or decline with your account"),
        ]
    if kind == "clone_flirt_owe":
        return [text("text", "The Tag you give the copy (up to120 characters)")]
    if kind == "clone_flirt_escape":
        return [
            menu(
                "options", "Accept Helplessness or actually escape", ("helpless", "damage", "play")
            ),
            entities(
                "denied",
                "Asset to damage only if escaping by damage",
                [x for x in data["assets"] if not x["damaged"]],
                0,
                1,
                False,
            ),
        ]
    raise WorkflowError("This original copy response is unavailable")


async def open_clone(interaction: discord.Interaction, service: CloneService) -> None:
    own = await asyncio.to_thread(service.view, viewer_from_interaction(interaction))
    if not own["owned"]:
        raise WorkflowError("Acquire the actual original copy first")
    ref = ActorRef.model_validate(own["actor"])
    channel = int(interaction.channel_id or 0)
    owed = await asyncio.to_thread(
        service.game.own_obligations, viewer_from_interaction(interaction)
    )
    follow = [
        x
        for x in owed
        if x["kind"] == "clone_flirt_followthrough"
        and ActorRef.model_validate_json(x["details"]["actor"]) == ref
    ]

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        mode = values["mode"][0]
        if mode == "keep":
            from girlframe.discord_adapter.m3_actor_plays import open_actor_play

            await open_actor_play(current, service.game, ref)
            return None
        actor_service = ActorPlayService(service.game)
        data = await asyncio.to_thread(
            actor_service.preview, viewer_from_interaction(current), channel, ref
        )
        fields = [text("context", "Describe the actual interaction")]
        if mode == "follow":
            fields.append(
                Field(
                    "obligation",
                    "Actual owed follow-through",
                    tuple((x["id"], x["details"]["wanted"]) for x in follow),
                )
            )
        else:
            targets = [x for x in data["opponents"] if x["ref"]["kind"] == "pilot"]
            fields += [
                Field("target", "Actual Girl", tuple((x["token"], x["name"]) for x in targets)),
                entities(
                    "identity",
                    "Own unmarked Identity (optional)",
                    [x for x in data["actor"]["identities"] if not x["marked"]],
                    0,
                    1,
                    False,
                ),
                menu("gain", "Heat gained if marking", ("1", "2", "3")),
                menu("heat", "Shared Heat to spend", tuple(str(x) for x in range(own["heat"] + 4))),
            ]

        async def submit(actual: discord.Interaction, answer: dict[str, Any]) -> str:
            if mode == "follow":
                result = await asyncio.to_thread(
                    service.fulfill_followthrough,
                    viewer_from_interaction(actual),
                    str(actual.id),
                    answer["obligation"][0],
                    answer["context"],
                    channel=channel,
                )
            else:
                target = next(x for x in targets if x["token"] == answer["target"][0])
                selected = answer.get("identity", ())
                result = await asyncio.to_thread(
                    actor_service.begin,
                    viewer_from_interaction(actual),
                    str(actual.id),
                    channel,
                    ref,
                    data["actor"]["source_sha256"],
                    ActorRef.model_validate(data["adjudicator"]["ref"])
                    if data["adjudicator"]["ref"]
                    else None,
                    data["cast_revision"],
                    PlayInput(
                        play="flirt",
                        context=answer["context"],
                        heat=int(answer["heat"][0]),
                        identity=selected[0] if selected else None,
                        gain=int(answer["gain"][0]) if selected else 0,
                        target_actor=ActorRef.model_validate(target["ref"]),
                        trigger_confirmed=True,
                    ),
                )
            return "Actual copy Play requested: " + str(result["action_id"])

        await NativeForm(
            current.user.id,
            "Clone AM: actual source",
            "The real scene lock and original-person responses apply.",
            fields,
            submit,
        ).present(current)
        return None

    options = [("keep", "Keep Your Head / owed rejection"), ("flirt", "Flirt")]
    if follow:
        options.append(("follow", "Follow through on her actual request"))
    await NativeForm(
        interaction.user.id,
        "Clone AM",
        f"Shared Heat: {own['heat']}. Own Identity: {own['identity']['name']}. "
        "Join the copy through Cast before acting.",
        [Field("mode", "Actual copy action", tuple(options))],
        choose,
    ).present(interaction)


async def open_purchase(interaction: discord.Interaction, service: CloneService) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction))
    if not data["available"]:
        raise WorkflowError("No reviewed Clone AM acquisition is available")
    if data["suspended"]:
        await reply(
            interaction, "This Class Requisition is suspended. Restore its original paid source."
        )
        return
    if data["owned"]:
        await open_clone(interaction, service)
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
            f"Clone AM acquired for {data['price']} Permissions. Open Clone AM in the actual scene."
        )

    await NativeForm(
        interaction.user.id,
        f"Clone AM — {data['kind'].replace('_', ' ').title()}, {data['price']} Permissions",
        "A separate Frame-resident copy with one Perfect Copy Identity, own Tags and Bonds, "
        "and your one shared Heat pool. It cannot Dive Deep.",
        (
            [Field("donor", "Choose the actual donor Frame", tuple((x, x) for x in data["donors"]))]
            if data["donors"]
            else []
        )
        + [Field("account", "Record the actual acquisition", paragraph=True)],
        submit,
    ).present(interaction)
