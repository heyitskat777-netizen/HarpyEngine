"""Owned real Living Battery roll/choices and private brain response."""

import asyncio
import json
from typing import Any, Literal, cast

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError


async def open_battery(
    interaction: discord.Interaction, game: GameService, target: ActorRef | None = None
) -> None:
    from girlframe.discord_adapter.m3_frame_control import open_neural_links
    from girlframe.services.m3_frame_control import FrameControlService
    from girlframe.services.m3_janus_play import preview

    viewer = viewer_from_interaction(interaction)
    if interaction.channel_id is None:
        raise WorkflowError("Use the actual source scene channel")
    data = await asyncio.to_thread(preview, game, viewer, interaction.channel_id, target)
    if not data["available"]:
        raise WorkflowError("Register the actual original Core and join as her actual JANUS Pilot")
    if target is None and len(data["targets"]) > 1:
        from girlframe.discord_adapter.m3_punishments import Picker

        choices = {x["token"]: x for x in data["targets"]}

        async def choose(current: discord.Interaction, value: str) -> None:
            await open_battery(current, game, ActorRef.model_validate(choices[value]["ref"]))

        await Picker(
            viewer.user_id,
            "Actual Universal Plug battery",
            tuple((token, x["label"]) for token, x in choices.items()),
            choose,
        ).show(interaction)
        return
    if data["connection"] is None:
        await open_neural_links(
            interaction,
            FrameControlService(game),
            ActorRef.model_validate(data["actor"]),
            ActorRef.model_validate(data["target"]),
        )
        return
    if data["rolled"]:
        from girlframe.discord_adapter.m3_frame_control import open_connection

        await open_connection(
            interaction, FrameControlService(game), data["connection"]["connection"]
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if current.channel_id is None:
            raise WorkflowError("Use the actual source scene channel")
        result = await asyncio.to_thread(
            game.begin,
            viewer_from_interaction(current),
            str(current.id),
            int(current.channel_id),
            data["sheet_revision"],
            PlayInput(
                play="living_battery",
                heat=0,
                target_actor=ActorRef.model_validate(data["target"]),
                context=values["account"],
                trigger_confirmed=True,
                identity=next(iter(values.get("identity", ())), None),
                gain=int(next(iter(values.get("gain", ("0",))), "0")),
                disposable_heat=cast(
                    Literal[0, 3, 4], int(next(iter(values.get("disposable_heat", ("0",))), "0"))
                ),
            ),
        )
        return "Living Battery prepared; actual chat lock precedes the one roll. Action " + str(
            result["action_id"]
        )

    fields = [Field("account", "Actual use of your reviewed neural link", paragraph=True)]
    if data.get("disposal_identities"):
        fields.extend(
            [
                Field(
                    "identity",
                    "Optional actual Identity to remove",
                    tuple((x["id"], x["label"]) for x in data["disposal_identities"]),
                    0,
                    1,
                    required=False,
                ),
                Field(
                    "gain",
                    "Heat from marking, if removing an Identity",
                    tuple((str(x), str(x)) for x in range(4)),
                ),
                Field(
                    "disposable_heat",
                    "Optional Identity disposal: additional Heat",
                    (("0", "Do not remove an Identity"), ("3", "+3 Heat"), ("4", "+4 Heat")),
                ),
            ]
        )
    form = NativeForm(
        viewer.user_id,
        "Living Battery — actual connected Core",
        "Roll 2d6 + one per actual battery Tag. This spends no Heat. "
        "Private questions remain with the two actual minds.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_battery_choice(
    interaction: discord.Interaction, game: GameService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(game.decision, viewer, identity)
    detail, kind = data["janus"], data["kind"]
    if kind == "janus_pandora_child":
        from girlframe.discord_adapter.m3_janus_requisitions import open_pandora_child

        await open_pandora_child(interaction, game, identity)
        return
    if kind == "janus_void_threshold":
        from girlframe.discord_adapter.m3_void import open_void
        from girlframe.services.m3_void import VoidService

        await open_void(interaction, VoidService(game.store), data["body"]["work_id"])
        return
    if kind == "janus_answer":
        fields = [Field("answer", "Your private brain response", paragraph=True)]
        text = "Actual private question: " + detail["question"]
    elif kind == "janus_erase":
        fields = (
            [
                Field(
                    "tags",
                    "Erase one actual battery Tag",
                    tuple((x["id"], x["label"]) for x in detail["tags"]),
                )
            ]
            if detail["tags"]
            else [
                Field("none", "Actual current Tags", (("none", "No actual Tag exists to erase"),))
            ]
        )
        text = "The known low result erases one actual Tag, then grants one printed choice."
    else:
        fields = [
            Field(
                "choices",
                "Choose printed benefits",
                tuple((x["id"], x["label"]) for x in detail["options"]),
                minimum=detail["count"],
                maximum=detail["count"],
            ),
            Field(
                "heat",
                "Heat only if selected",
                (("0", "No Heat option"),) + tuple((str(n), str(n) + " Heat") for n in range(1, 5)),
            ),
            Field(
                "question",
                "Private brain question, only if selected",
                paragraph=True,
                required=False,
            ),
        ]
        if detail.get("universal"):
            fields.append(Field("tag", "Optional real Universal Plug Tag", required=False))
        if detail["identities"]:
            fields.append(
                Field(
                    "identities",
                    "Unmark up to two, only if selected",
                    tuple((x["id"], x["label"]) for x in detail["identities"]),
                    minimum=0,
                    maximum=min(2, len(detail["identities"])),
                    required=False,
                )
            )
        text = (
            "Choose exactly the final result's distinct benefits; "
            "details apply only to selected options."
        )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if kind == "janus_answer":
            answer = ChoiceAnswer(text=values["answer"])
        elif kind == "janus_erase":
            answer = ChoiceAnswer(options=tuple(values.get("tags", ())))
        else:
            answer = ChoiceAnswer(
                options=tuple(values["choices"]),
                number=int(values["heat"][0]),
                text=values.get("question", ""),
                fields={"identities": json.dumps(list(values.get("identities", ())))}
                | ({"tag": values["tag"]} if values.get("tag", "").strip() else {}),
            )
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            answer,
        )
        return "Actual owned neural-link response saved. Private answers remain private."

    form = NativeForm(viewer.user_id, "Living Battery — owned response", text, fields, submit)
    await reply(interaction, form.text(), form)


async def open_brain_link(
    interaction: discord.Interaction, game: GameService, identity: str
) -> None:
    from girlframe.services.m3_janus_play import BatteryService

    viewer = viewer_from_interaction(interaction)
    service = BatteryService(game)
    data = await asyncio.to_thread(service.get, viewer, identity)
    transcript = "Question: " + data["question"] + "\nAnswer: " + (data["answer"] or "Pending")
    for entry in data["messages"][-8:]:
        author = "You" if entry["controller"] == viewer.user_id else "Other mind"
        transcript += "\n" + author + ": " + entry["text"]
    if not data["can_send"]:
        await reply(
            interaction, "Private brain link (" + data["phase"] + ")\n" + transcript[-1500:]
        )
        return
    actors = {ActorRef.model_validate(x).token: ActorRef.model_validate(x) for x in data["actors"]}

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> None:
        await asyncio.to_thread(
            service.send,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            actors[values["speaker"][0]],
            values["message"],
        )
        await open_brain_link(current, game, identity)
        return None  # Preserve the actual next private screen after real Confirm.

    form = NativeForm(
        viewer.user_id,
        "Your private brain link",
        transcript[-1500:],
        [
            Field(
                "speaker",
                "Your actual linked mind",
                tuple(
                    (token, "JANUS Pilot" if actor.kind == "pilot" else "Harpy Core")
                    for token, actor in actors.items()
                ),
            ),
            Field("message", "Your private brain message", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
