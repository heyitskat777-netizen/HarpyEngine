"""Owned actual-role Play and known-roll recovery controls."""

from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm, threaded
from girlframe.discord_adapter.m2_ui import entities, menu, one, text
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actor_plays import ActorPlayService


async def open_actor_play(
    interaction: discord.Interaction, game: GameService, ref: ActorRef
) -> None:
    service = ActorPlayService(game)
    viewer, channel = viewer_from_interaction(interaction), interaction.channel_id or 0
    data = await threaded(lambda: service.preview(viewer, channel, ref))
    actor = data["actor"]
    owed = await threaded(lambda: game.own_obligations(viewer))
    rejections = {
        x["id"]: x
        for x in owed
        if x["kind"] == "actor_reject_tag"
        and ActorRef.model_validate_json(x["details"]["actor"]) == ref
    }
    options = (("keep_your_head", "Keep Your Head"),) + tuple(
        ("reject:" + key, "Take action to reject an owed Tag") for key in rejections
    )

    async def choose(current: discord.Interaction, token: str) -> None:
        rejection = token[7:] if token.startswith("reject:") else None
        fields = [
            text(
                "context",
                "What are you trying to make it through?"
                if rejection is None
                else "Describe your action to reject this Tag",
            )
        ]
        if rejection is None:
            fields.extend(
                [
                    entities(
                        "identity",
                        "Mark an ordinary Identity (optional)",
                        [x for x in actor["identities"] if not x["marked"]],
                        0,
                        1,
                        False,
                    ),
                    menu("gain", "Heat gained when marking", ("1", "2", "3")),
                    menu("heat", "Heat to spend", tuple(str(x) for x in range(actor["heat"] + 4))),
                ]
            )
        fields.append(
            Field(
                "confirm",
                "Confirm the Play and its responding Director",
                (("yes", "Confirm and request scene lock"),),
            )
        )

        async def submit(response: discord.Interaction, values: dict[str, Any]) -> str:
            identity = one(values, "identity") if rejection is None else None
            result = await threaded(
                lambda: service.begin(
                    viewer_from_interaction(response),
                    str(response.id),
                    channel,
                    ref,
                    actor["source_sha256"],
                    ActorRef.model_validate(data["adjudicator"]["ref"]),
                    data["cast_revision"],
                    PlayInput(
                        play="actor_reject_tag" if rejection else token,
                        context=values["context"],
                        trigger_confirmed=True,
                        heat=int(one(values, "heat", "0")),
                        identity=identity,
                        gain=int(one(values, "gain", "0")) if identity else 0,
                    ),
                    rejection=rejection,
                )
            )
            return (
                "Play saved: "
                + str(result["action_id"])
                + ". Chat will pause before the action proceeds. "
                "Resume your responses with /choice resume."
            )

        form = NativeForm(
            viewer.user_id,
            "Your actual Handler role",
            "Your Director for Handler-rule replies is "
            + data["adjudicator"]["label"]
            + ". Your Heat and Identities belong to this Director-presence context. "
            "Confirm before anything is spent.",
            fields,
            submit,
        )
        await reply(current, form.text(), form)

    await Picker(
        viewer.user_id,
        "**Your Handler under Girl rules**\nChoose a Play or owed Tag rejection in this scene.",
        options,
        choose,
    ).show(interaction)


async def open_recovery(
    interaction: discord.Interaction, game: GameService, saved: dict[str, Any]
) -> None:
    service = ActorPlayService(game)

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await threaded(
            lambda: service.recover(
                viewer_from_interaction(current),
                str(current.id),
                saved["id"],
                saved["revision"],
                cancel=one(values, "operation") == "cancel",
            )
        )
        return (
            "Unrolled Play cancelled."
            if result["cancelled_unrolled"]
            else "Your saved Play will reacquire its chat lock. "
            "The receipt, resource spending and prior answers are preserved. Reopen /choice resume."
        )

    options: tuple[tuple[str, str], ...] = (("resume", "Resume the saved Play"),)
    if not saved["rolled"]:
        options += (("cancel", "Cancel this unrolled Play"),)
    form = NativeForm(
        interaction.user.id,
        "Recover your actual-role Play",
        "Staff must first restore the channel permissions. "
        "A known roll cannot be discarded or repeated.",
        [Field("operation", "Recovery", options)],
        submit,
    )
    await reply(interaction, form.text(), form)
