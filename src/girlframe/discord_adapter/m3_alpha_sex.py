"""Voluntary original-source setup and real owned Alpha intimacy outcomes."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_alpha_sex import SexService


async def open_alpha(interaction: discord.Interaction, service: SexService) -> None:
    viewer = viewer_from_interaction(interaction)
    channel = int(interaction.channel_id or 0)
    data = await asyncio.to_thread(service.menu, viewer, channel)
    options = [("invite", "Confirm a voluntary source interaction")] if data["targets"] else []
    options += [
        ("consent:" + x["id"], "Answer your source invitation")
        for x in data["sessions"]
        if x["phase"] == "invited" and x["counterpart"] == viewer.user_id
    ]
    options += [
        ("track:" + x["id"], "Find original counterpart by smell")
        for x in data["sessions"]
        if x["tracking"] and x["caster"] == viewer.user_id
    ]
    if any(x["phase"] == "accepted" and x["caster"] == viewer.user_id for x in data["sessions"]):
        options.append(("play", "Prepare the accepted Alpha Sex Play"))
    if not options:
        await reply(
            interaction,
            "No current supported Alpha interaction. Source invitations "
            "and accepted interactions are saved here for their actual original participants.",
        )
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        selected = values["action"][0]
        if selected == "play":
            from girlframe.discord_adapter.m2_ui import open_play

            await open_play(current, service.game)
            return None
        if selected.startswith("track:"):
            located = await asyncio.to_thread(
                service.track, viewer_from_interaction(current), selected.removeprefix("track:")
            )
            return (
                "Actual original "
                + str(located["label"])
                + " is at "
                + str(located["cell"])
                + ". No movement was performed."
            )
        if selected.startswith("consent:"):
            identity = selected.removeprefix("consent:")
            fields = [
                Field(
                    "accept",
                    "This actual interaction was voluntary",
                    (("yes", "Confirm this actual source"), ("no", "Decline this source")),
                ),
                Field("account", "Your own source confirmation or refusal", paragraph=True),
            ]

            async def respond(response: discord.Interaction, answer: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.respond,
                    viewer_from_interaction(response),
                    str(response.id),
                    identity,
                    data["revision"],
                    answer["accept"][0] == "yes",
                    answer["account"],
                )
                return "Your own source response is saved. No consent to other actions is inferred."

            form = NativeForm(
                current.user.id,
                "Your source answer",
                "Answer only for your "
                "original character. Safety pause remains available. No reply is fabricated.",
                fields,
                respond,
            )
        else:
            fields = [
                Field(
                    "target",
                    "Actual original counterpart",
                    tuple(
                        (ActorRef.model_validate(x["ref"]).token, x["label"])
                        for x in data["targets"]
                    ),
                ),
                Field("account", "Your actual voluntary source interaction", paragraph=True),
            ]

            async def invite(response: discord.Interaction, answer: dict[str, Any]) -> str:
                target = next(
                    x
                    for x in data["targets"]
                    if ActorRef.model_validate(x["ref"]).token == answer["target"][0]
                )
                result = await asyncio.to_thread(
                    service.invite,
                    viewer_from_interaction(response),
                    str(response.id),
                    channel,
                    ActorRef.model_validate(target["ref"]),
                    data["revision"],
                    answer["account"],
                )
                return (
                    "Source invitation saved. The actual counterpart answers in /campaign alpha. "
                    + str(result["id"])
                )

            form = NativeForm(
                current.user.id,
                "Alpha: source interaction",
                "This creates no "
                "dice or effects. The actual counterpart must confirm their own voluntary source.",
                fields,
                invite,
            )
        await reply(current, form.text(), form)
        return None

    form = NativeForm(
        viewer.user_id,
        "Alpha controls",
        "Owned source interactions and active "
        "scent tracking. Gameplay requires the existing scoped rules release.",
        [Field("action", "Current source controls", tuple(options))],
        choose,
    )
    await reply(interaction, form.text(), form)


async def open_consent(
    interaction: discord.Interaction, service: SexService, identity: str
) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    if not data["can_answer"]:
        await reply(interaction, "This original source is " + data["phase"] + ".")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["accept"][0] == "yes",
            values["account"],
        )
        return "Your actual source answer is saved; no other consent or action is inferred."

    form = NativeForm(
        interaction.user.id,
        "Your original Alpha source",
        "Proposed source: "
        + data["proposal"]
        + " Only your own actual voluntary source may be confirmed.",
        [
            Field("accept", "Your actual source answer", (("yes", "Confirm"), ("no", "Decline"))),
            Field("account", "Your own factual answer", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_alpha_choice(
    interaction: discord.Interaction, game: GameService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(game.decision, viewer, identity)
    if data["kind"].startswith("battle_"):
        from girlframe.discord_adapter.m3_battle import open_battle

        await open_battle(interaction, game, identity)
        return
    if data["kind"] == "alpha_sex_punishment":
        from girlframe.discord_adapter.m3_role_punishments import open_role_punishment
        from girlframe.services.m3_role_punishments import RolePunishmentService

        await open_role_punishment(interaction, RolePunishmentService(game), data["body"]["case"])
        return
    if data["kind"] == "alpha_sex_counter_play":
        from girlframe.discord_adapter.m2_ui import open_play

        await open_play(interaction, game, parent=data, _pilot=True)
        return
    detail = data["alpha_sex"]
    if data["kind"] == "alpha_sex_damage":
        fields = [
            Field(
                "asset",
                "Damage one actual Girl Asset",
                tuple((x["id"], x["label"]) for x in detail["assets"]),
            )
        ]
    elif data["kind"] == "alpha_sex_low":
        choices = [("pass", "Decline this opportunity")]
        if detail["items"]:
            choices.append(("take", "Take one actual accessible held object"))
        if detail["can_counter"]:
            choices.append(("play", "Make a genuine ordinary Play"))
        if detail["can_punish"]:
            choices.append(("punish", "Inflict a real supported Punishment"))
        fields = [Field("opportunity", "Your one opportunity without reprisal", tuple(choices))]
        if detail["items"]:
            fields += [
                Field(
                    "item",
                    "If taking: actual accessible object",
                    tuple((x["id"], x["label"]) for x in detail["items"]),
                    minimum=0,
                    required=False,
                ),
                Field(
                    "account",
                    "If taking: describe actually taking it",
                    paragraph=True,
                    required=False,
                ),
            ]
    elif data["kind"] == "alpha_sex_wake":
        fields = [Field("account", "Actually waking from this source sleep", paragraph=True)]
    else:
        raise ValueError("Unsupported Alpha source choice")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if data["kind"] == "alpha_sex_damage":
            answer = ChoiceAnswer(options=(values["asset"][0],))
        elif data["kind"] == "alpha_sex_wake":
            answer = ChoiceAnswer(options=("wake",), text=values["account"])
        else:
            choice = values["opportunity"][0]
            answer = ChoiceAnswer(
                options=(choice,),
                text=values.get("account", "") if choice == "take" else "",
                fields={"item": values["item"][0]} if choice == "take" else {},
            )
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            answer,
        )
        return "Your real source response is saved. Required effects and the owned wake remain."

    form = NativeForm(
        viewer.user_id,
        "Alpha: " + data["kind"].replace("alpha_sex_", ""),
        "Only actual source effects apply. Safety pause remains available; no "
        "objects, answers, movement or reprisal are invented.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)
