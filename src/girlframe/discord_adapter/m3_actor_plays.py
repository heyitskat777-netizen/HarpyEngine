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
    interaction: discord.Interaction,
    game: GameService,
    ref: ActorRef,
    *,
    parent: dict[str, Any] | None = None,
    source_work: str | None = None,
    channel: int | None = None,
) -> None:
    service = ActorPlayService(game)
    viewer = viewer_from_interaction(interaction)
    channel = (
        int(parent["channel"])
        if parent
        else channel
        if channel is not None
        else interaction.channel_id or 0
    )
    data = await threaded(lambda: service.preview(viewer, channel, ref))
    actor = data["actor"]
    owed = await threaded(lambda: game.own_obligations(viewer))
    rejections = {
        x["id"]: x
        for x in owed
        if x["kind"] == "actor_reject_tag"
        and ActorRef.model_validate_json(x["details"]["actor"]) == ref
    }
    harpy_mode = actor.get("girl") == "harpy"
    basic = (("keep_your_head", "Keep Your Head"),) + (
        (
            ("dive_deep", "Dive Deep"),
            ("check_sensors", "Check Sensors — honest questions"),
            ("engage", "Engage the Enemy"),
            ("go_off_duty", "Go Off-Duty — hide in Voidspace"),
        )
        if harpy_mode
        else ()
    )
    options = ((("dive_deep", "Required Dive Deep"),) if source_work else basic) + (
        tuple(("reject:" + key, "Take action to reject an owed Tag") for key in rejections)
        if parent is None and source_work is None
        else ()
    )
    if (harpy_mode or actor["rules"] == "handler_girl") and parent is None and source_work is None:
        options += (("handler_tags", "Use an observed Handler Tag"),)
        if any(
            x in data.get("retained_plays", [])
            for x in ("girl.mockingbird.bad-at-being-a-person", "girl.mockingbird.sex-play")
        ):
            options += (("mockingbird", "Retained Mockingbird Plays"),)
    if not source_work:
        if data.get("snoop_targets"):
            options += (("snoop", "Snoop — actual known person's stuff"),)
        if data.get("enforcement_targets"):
            options += (("enforcement_initiative", "Enforcement Initiative — take hold"),)

    async def choose(current: discord.Interaction, token: str) -> None:
        if token == "handler_tags":
            from girlframe.discord_adapter.m3_handler_tags import open_handler_tags

            await open_handler_tags(current, game, actor=ref)
            return
        if token == "mockingbird":
            from girlframe.discord_adapter.m3_mockingbird_plays import open_book

            await open_book(current, game, actor_ref=ref)
            return
        rejection = token[7:] if token.startswith("reject:") else None
        sensors = token == "check_sensors"
        resting = token == "go_off_duty"
        manual = bool(source_work and token in data.get("forbidden_plays", []))
        fields = [
            text(
                "context",
                "What questions do you ask?"
                if sensors
                else "What are you trying to make it through?"
                if rejection is None
                else "Describe your action to reject this Tag",
            )
        ]
        if token in ("engage", "snoop", "enforcement_initiative"):
            opponents = data.get(
                "snoop_targets"
                if token == "snoop"
                else "enforcement_targets"
                if token == "enforcement_initiative"
                else "opponents",
                [],
            )
            if parent and parent.get("body", {}).get("attacker"):
                opponents = [x for x in opponents if x["ref"] == parent["body"]["attacker"]]
            if not opponents:
                await reply(current, "Join the actual opposing actor to this scene first.")
                return
            fields.append(
                Field(
                    "opponent",
                    "Actual battlefield opponent",
                    tuple(
                        (x["token"], x.get("name", x.get("label", "Actual person")))
                        for x in opponents
                    ),
                )
            )
            if token in ("snoop", "enforcement_initiative"):
                fields.append(
                    Field(
                        "piloting",
                        "Are you acting through your actual linked Frame?",
                        (("no", "No — my actual body"), ("yes", "Yes — my actual Frame")),
                    )
                )
        if token == "keep_your_head" and data.get("pavlov"):
            fields.extend(
                [
                    Field(
                        "obeying_orders",
                        "Are you currently obeying orders?",
                        (
                            ("no", "No"),
                            ("yes", "Yes — my actual current circumstances"),
                        ),
                    ),
                    text("order_account", "What orders are you obeying? (if yes)", False),
                ]
            )
        if rejection is None and not sensors and not manual and not resting:
            fields.extend(
                [
                    entities(
                        "identity",
                        "Mark an ordinary Identity (optional)",
                        [x for x in actor["identities"] if not x["marked"] and not x["paired"]],
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
                "Confirm the Play and its adjudicator",
                (("yes", "Confirm and request scene lock"),),
            )
        )

        async def submit(response: discord.Interaction, values: dict[str, Any]) -> str:
            identity = (
                one(values, "identity")
                if rejection is None and not sensors and not manual and not resting
                else None
            )
            result = await threaded(
                lambda: service.begin(
                    viewer_from_interaction(response),
                    str(response.id),
                    channel,
                    ref,
                    actor["source_sha256"],
                    ActorRef.model_validate(data["adjudicator"]["ref"])
                    if data["adjudicator"]["ref"]
                    else None,
                    data["cast_revision"],
                    PlayInput(
                        play="actor_reject_tag" if rejection else token,
                        context=values["context"],
                        trigger_confirmed=True,
                        heat=0 if manual or resting else int(one(values, "heat", "0")),
                        identity=identity,
                        gain=int(one(values, "gain", "0")) if identity else 0,
                        parent=parent["action_id"] if parent else None,
                        source_work=source_work,
                        obeying_orders=one(values, "obeying_orders", "no") == "yes",
                        order_account=values.get("order_account", ""),
                        target_actor=next(
                            ActorRef.model_validate(x["ref"])
                            for x in opponents
                            if x["token"] == one(values, "opponent")
                        )
                        if token in ("engage", "snoop", "enforcement_initiative")
                        else None,
                        piloting=one(values, "piloting", "no") == "yes",
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
            "Your Harpy" if harpy_mode else "Your actual Handler role",
            "Your rules adjudicator is "
            + data["adjudicator"]["label"]
            + (
                ". Ask any questions; this spends no Heat and rolls no dice. "
                if sensors
                else ". Your forbidden mandatory Dive needs an actual written adjudication; "
                "no Heat or Identity is spent, and no dice are rolled. "
                if manual
                else ". Hide in Voidspace with one base-zero roll, "
                "without Heat or Identity spending. "
                if resting
                else ". This uses your Harpy's own Heat and Identities. "
                if harpy_mode
                else ". Your Heat and Identities belong to this Director-presence context. "
            )
            + "Confirm before anything is spent.",
            fields,
            submit,
        )
        await reply(current, form.text(), form)

    await Picker(
        viewer.user_id,
        ("**Your Harpy**" if harpy_mode else "**Your Handler under Girl rules**")
        + "\nChoose a Play or owed Tag rejection in this scene.",
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
