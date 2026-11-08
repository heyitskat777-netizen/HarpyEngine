"""Private voluntary source and actual owned Princess intimacy decisions."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_princess_sex as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_princess_sex import SexService

DISCLOSURE = (
    "Confirm only your own actual voluntary interaction. On a high result the Princess "
    "chooses one immediately required Play and makes every actor-owned decision for you "
    "during that Play, including the necessary decision fields. Other people's decisions "
    "and safety controls remain theirs. No reply or further consent is inferred."
)


async def open_princess(
    interaction: discord.Interaction, service: SexService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    channel = int(interaction.channel_id or 0)
    if identity is None:
        data = await asyncio.to_thread(service.menu, viewer, channel)
        options = [("invite", "Propose your actual voluntary source")] if data["targets"] else []
        options += [(x["id"], "Saved interaction: " + x["phase"]) for x in data["sessions"]]
        if not options:
            await reply(interaction, "No supported current Princess interaction in this scene.")
            return

        async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
            selected = values["action"][0]
            if selected != "invite":
                await open_princess(current, service, selected)
                return None

            async def invite(response: discord.Interaction, answer: dict[str, Any]) -> str:
                target = next(x for x in data["targets"] if x["token"] == answer["target"][0])
                await asyncio.to_thread(
                    service.invite,
                    viewer_from_interaction(response),
                    str(response.id),
                    channel,
                    ActorRef.model_validate(target["ref"]),
                    data["revision"],
                    answer["account"],
                )
                return "Saved. The actual counterpart answers their own private source invitation."

            await NativeForm(
                current.user.id,
                "Princess source",
                DISCLOSURE,
                [
                    Field(
                        "target",
                        "Actual original counterpart",
                        tuple((x["token"], x["label"]) for x in data["targets"]),
                    ),
                    Field("account", "Your actual voluntary source interaction", paragraph=True),
                ],
                invite,
            ).present(current)
            return None

        await NativeForm(
            viewer.user_id,
            "Princess controls",
            DISCLOSURE,
            [Field("action", "Owned source", tuple(options))],
            choose,
        ).present(interaction)
        return
    data = await asyncio.to_thread(service.view, viewer, identity)
    if data["phase"] == "invited" and data["counterpart"] == viewer.user_id:

        async def confirm(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.confirm,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["accept"][0] == "yes",
                values["account"],
            )
            return "Your own disclosed source response is saved."

        await NativeForm(
            viewer.user_id,
            "Your Princess source answer",
            DISCLOSURE + " Proposed source: " + data["proposal"],
            [
                Field(
                    "accept",
                    "Your actual voluntary source",
                    (("yes", "Confirm"), ("no", "Decline")),
                ),
                Field("account", "Your own actual answer", paragraph=True),
            ],
            confirm,
        ).present(interaction)
        return
    if data["phase"] == "accepted" and data["caster"] == viewer.user_id:
        sheet = await asyncio.to_thread(service.game.sheet, viewer)

        async def begin(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.game.begin,
                viewer_from_interaction(current),
                str(current.id),
                channel,
                sheet["revision"],
                PlayInput(
                    play=rules.PLAY,
                    target_actor=ActorRef.model_validate(data["target"]),
                    source_work=identity,
                    context=values["context"],
                    trigger_confirmed=True,
                    heat=int(values["heat"][0]),
                    identity=next(iter(values.get("identity", ())), None),
                    gain=int(values.get("gain", ("0",))[0]),
                ),
            )
            return "Actual original Play prepared. Continue its saved choices. " + str(
                result["action_id"]
            )

        heat = sheet["heat"]
        await NativeForm(
            viewer.user_id,
            "Prepare Princess Sex Play",
            DISCLOSURE,
            [
                Field("context", "Your actual confirmed interaction", paragraph=True),
                Field(
                    "identity",
                    "Optional own Identity to mark",
                    tuple((x["id"], x["name"]) for x in sheet["identities"] if not x["marked"]),
                    minimum=0,
                    required=False,
                ),
                Field(
                    "gain", "Actual Identity Heat gained", tuple((str(n), str(n)) for n in range(6))
                ),
                Field(
                    "heat",
                    "Heat to spend",
                    tuple((str(n), str(n)) for n in range(heat + 6)),
                ),
            ],
            begin,
        ).present(interaction)
        return
    choices = await asyncio.to_thread(service.game.choices, viewer)
    row = next(
        (
            x
            for x in choices
            if x["kind"] == "princess_sex_child" and x["action_id"] == data["action"]
        ),
        None,
    )
    if row:
        await open_choice(interaction, service.game, row["id"])
        return
    await reply(
        interaction,
        "Saved private Princess interaction: "
        + data["phase"]
        + ". Continue your actual owned decisions in Play controls or Inbox.",
    )


async def open_choice(interaction: discord.Interaction, game: GameService, identity: str) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(game.decision, viewer, identity)
    kind, detail = data["kind"], data["princess_sex"]
    service = SexService(game)
    source = await asyncio.to_thread(service.view, viewer, detail["session"])
    if kind == "princess_sex_child":
        child = source["child"]
        nightmare = {"owned": True} if child["nightmare"] else None
        fields = [
            Field(
                "heat",
                "Actual counterpart Heat to spend",
                tuple((str(n), str(n)) for n in ((0,) if nightmare else range(child["heat"] + 6))),
            )
        ]
        fields += [
            Field(
                "identity",
                "Optional actual Identity to mark",
                tuple((x["id"], x["name"]) for x in child["identities"]),
                minimum=0,
                required=False,
            ),
            Field("gain", "Actual Identity Heat gained", tuple((str(n), str(n)) for n in range(6))),
        ]
    elif kind == "princess_sex_direct":
        fields = [
            Field(
                "play",
                "Immediately required supported Play",
                (("keep_your_head", "Keep Your Head"),),
            ),
            Field("text", "Actual immediate pressure and action", paragraph=True),
        ]
    elif kind == "princess_sex_favour_reply":
        fields = [
            Field(
                "options",
                "Your own actual favour response",
                (("agree", "Agree"), ("refuse", "Refuse")),
            ),
            Field("text", "Your own actual response", paragraph=True),
        ]
    elif kind == "princess_sex_optional_tag":
        fields = [
            Field(
                "options",
                "Your optional ordinary Tag",
                (("give", "Give a Tag"), ("decline", "Decline")),
            ),
            Field("text", "If giving: actual Tag", required=False),
        ]
    else:
        fields = [
            Field(
                "text",
                "Actual Tag" if kind == "princess_sex_low_tag" else "Your actual requested favour",
                paragraph=True,
            )
        ]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if kind == "princess_sex_child":
            result = await asyncio.to_thread(
                game.begin,
                viewer_from_interaction(current),
                str(current.id),
                data["channel"],
                child["sheet_revision"],
                PlayInput(
                    play="keep_your_head",
                    parent=source["action"],
                    source_work=source["direction"],
                    context=child["context"],
                    heat=int(values["heat"][0]),
                    identity=next(iter(values.get("identity", ())), None),
                    gain=int(values.get("gain", ("0",))[0]),
                    trigger_confirmed=True,
                ),
            )
            return "Actual counterpart child prepared under your one-Play authority. " + str(
                result["action_id"]
            )
        options = (
            (values["play"][0],)
            if kind == "princess_sex_direct"
            else tuple(values.get("options", ()))
        )
        text = "" if options == ("decline",) else values.get("text", "")
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            ChoiceAnswer(options=options, text=text),
        )
        return "Actual owned source decision saved."

    await NativeForm(
        viewer.user_id,
        "Princess: " + kind.removeprefix("princess_sex_"),
        "Actual original participants and one scoped child only. " + (detail["favour"] or ""),
        fields,
        submit,
    ).present(interaction)
