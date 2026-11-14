"""Private, actual-person Flirt and source-bound follow-through controls."""

from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm, threaded
from girlframe.discord_adapter.m2_ui import YES, entities, menu, one, text
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import FLIRT_QUESTIONS, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_actor_plays import ActorPlayService
from girlframe.services.onboarding import WorkflowError


def choice_fields(decision: dict[str, Any]) -> list[Field]:
    kind, result, data = decision["kind"], decision["result"], decision["harpy_flirt"]
    marked = [x for x in data["identities"] if x["marked"]]
    unmark = (
        entities(
            "denied",
            "Own actual marked Identities to unmark",
            marked,
            0,
            min(data["maximum"], len(marked)),
            False,
        )
        if marked
        else None
    )
    if kind == "harpy_flirt_actor":
        fields = [menu("options", "Ask one printed question", FLIRT_QUESTIONS)]
        if unmark:
            fields.append(unmark)
        if result["tier"] == "high":
            fields += [
                menu("fields.extra", "How do you go too far?", ("escape", "handler", "owe")),
                text("text", "Describe going too far"),
            ]
        return fields
    if kind == "harpy_flirt_target":
        low = result["tier"] == "low"
        fields = [text("text", "What pushes you away?" if low else "Answer her actual question")]
        if unmark:
            fields.append(unmark)
        fields.append(
            menu(
                "options",
                "Optional return question" if low else "Ask your printed question",
                FLIRT_QUESTIONS,
                0,
                1,
                False,
            )
        )
        if result.get("question") == "intimacy":
            fields.append(Field("flag", "My actual safety consent", YES, required=False))
        return fields
    if kind == "harpy_flirt_answer":
        fields = [text("text", "Answer her actual return question")]
        if result.get("return_question") == "intimacy":
            fields.append(Field("flag", "My actual safety consent", YES, required=False))
        return fields
    if kind == "harpy_flirt_followthrough_confirm":
        return [
            Field("flag", "Did the actual described follow-through happen?", YES),
            text("text", "Confirm or decline with your account"),
        ]
    if kind == "harpy_flirt_owe":
        return [text("text", "The Tag you give her (up to 120 characters)")]
    if kind == "harpy_flirt_escape":
        fields = [
            menu(
                "options", "Accept Helplessness or actually escape", ("helpless", "damage", "play")
            )
        ]
        assets = [x for x in data["assets"] if not x["damaged"]]
        if assets:
            fields.append(
                entities(
                    "denied", "Own Asset to damage only if escaping by damage", assets, 0, 1, False
                )
            )
        return fields
    raise WorkflowError("This original Harpy/Girl response is unavailable")


async def open_flirt(
    interaction: discord.Interaction,
    game: Any,
    ref: ActorRef,
    *,
    channel: int | None = None,
    parent: dict[str, Any] | None = None,
) -> None:
    service = ActorPlayService(game)
    channel = channel if channel is not None else int(interaction.channel_id or 0)
    data = await threaded(
        lambda: service.preview(viewer_from_interaction(interaction), channel, ref)
    )
    actor = data["actor"]
    targets = [x for x in data["opponents"] if x["ref"]["kind"] == "pilot"]
    if not targets:
        await reply(interaction, "Join the actual original Girl to this Flirt scene first.")
        return
    fields = [
        text("context", "Describe your actual interaction"),
        Field("target", "Actual original Girl", tuple((x["token"], x["name"]) for x in targets)),
    ]
    identities = [x for x in actor["identities"] if not x["marked"] and not x["paired"]]
    if identities:
        fields.append(
            entities("identity", "Own unmarked Identity (optional)", identities, 0, 1, False)
        )
    fields += [
        menu("gain", "Heat gained if marking", ("1", "2", "3")),
        menu("heat", "Own Heat to spend", tuple(str(x) for x in range(actor["heat"] + 4))),
    ]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        identity = one(values, "identity")
        target = next(x for x in targets if x["token"] == one(values, "target"))
        result = await threaded(
            lambda: service.begin(
                viewer_from_interaction(current),
                str(current.id),
                channel,
                ref,
                actor["source_sha256"],
                ActorRef.model_validate(data["adjudicator"]["ref"])
                if data["adjudicator"]["ref"]
                else None,
                data["cast_revision"],
                PlayInput(
                    play="flirt",
                    context=values["context"],
                    heat=int(one(values, "heat", "0")),
                    identity=identity,
                    gain=int(one(values, "gain", "0")) if identity else 0,
                    target_actor=ActorRef.model_validate(target["ref"]),
                    parent=parent["action_id"] if parent else None,
                    trigger_confirmed=True,
                ),
            )
        )
        return (
            "Flirt saved: "
            + str(result["action_id"])
            + ". Resume your own private responses with /choice resume."
        )

    await NativeForm(
        interaction.user.id,
        "Your actual Harpy — Flirt",
        "Use her actual Heat and Identities. Both people answer their own questions; "
        "follow-through is confirmed separately.",
        fields,
        submit,
    ).present(interaction)


async def open_followthrough(
    interaction: discord.Interaction,
    game: Any,
    obligation: dict[str, Any],
    *,
    channel: int | None = None,
) -> None:
    ref = ActorRef.model_validate_json(obligation["details"]["actor"])
    channel = channel if channel is not None else int(interaction.channel_id or 0)
    viewer = viewer_from_interaction(interaction)
    service = ActorPlayService(game)
    data = (
        await threaded(lambda: service.preview(viewer, channel, ref))
        if ref.kind != "pilot"
        else None
    )
    own = (
        await threaded(lambda: game.sheet(viewer, viewer.user_id)) if ref.kind == "pilot" else None
    )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        prepared = PlayInput(
            play="harpy_followthrough",
            heat=0,
            context=values["account"],
            source_work=obligation["id"],
            trigger_confirmed=True,
        )
        if data:
            result = await threaded(
                lambda: service.begin(
                    viewer_from_interaction(current),
                    str(current.id),
                    channel,
                    ref,
                    data["actor"]["source_sha256"],
                    ActorRef.model_validate(data["adjudicator"]["ref"])
                    if data["adjudicator"]["ref"]
                    else None,
                    data["cast_revision"],
                    prepared,
                )
            )
        else:
            assert own is not None
            result = await threaded(
                lambda: game.begin(
                    viewer_from_interaction(current),
                    str(current.id),
                    channel,
                    own["revision"],
                    prepared,
                )
            )
        return "Follow-through saved for the original recipient's confirmation: " + str(
            result["action_id"]
        )

    await NativeForm(
        interaction.user.id,
        "Actual Flirt follow-through",
        obligation["details"]["wanted"],
        [text("account", "Describe what actually happened")],
        submit,
    ).present(interaction)
