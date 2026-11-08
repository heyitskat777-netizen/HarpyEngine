"""Owned native Doll choices, substantive information and actual scene exit/re-entry."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_vatgrown import DollService


async def open_choice(
    interaction: discord.Interaction, game: GameService, decision: dict[str, Any]
) -> None:
    detail = decision["detail"]
    fields = []
    if detail["options"]:
        fields.append(
            Field(
                "options",
                "Your actual printed choice",
                tuple((x[0], x[1]) for x in detail["options"]),
                minimum=detail["minimum"],
                maximum=detail["maximum"],
            )
        )
    if detail["text"]:
        fields.append(
            Field(
                "text",
                detail["label"],
                paragraph=True,
                required=decision["kind"] == "vat_doll_information",
            )
        )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            decision["id"],
            decision["revision"],
            ChoiceAnswer(options=values.get("options", ()), text=values.get("text", "")),
        )
        return (
            "Your actual Doll choice or substantive reply is saved. "
            "Remaining human choices and real consequences keep their own controls."
        )

    instructions = (
        "Choose the printed quota. A nonempty question is actually speaking and ends "
        "quiet/object background presentation; blank means you have no questions and they offer "
        "a secret. OOC pause remains available."
    )
    if decision["kind"] == "vat_doll_information":
        instructions = (
            "Original actual question: "
            + (detail["question"] or "No question: offer an actual secret")
            + ". Author only your actual source reply, without importing "
            "another person's private notes."
        )
    form = NativeForm(
        interaction.user.id, "Unassuming Doll: your choice", instructions, fields, submit
    )
    await reply(interaction, form.text(), form)


async def open_vatgrown(
    interaction: discord.Interaction, service: DollService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    channel = int(interaction.channel_id or 0)
    if identity is not None:
        data = await asyncio.to_thread(service.view, viewer, identity)
        options = []
        if data["leave"]:
            options.append(("leave", "Actually leave the original scene without interception"))
        if data["departure"]:
            options.append(("return", "Actually return with a factual re-entry account"))
        if data["punishment"] and data["phase"] == "punishment":
            from girlframe.discord_adapter.m3_role_punishments import open_role_punishment
            from girlframe.services.m3_role_punishments import RolePunishmentService

            await open_role_punishment(
                interaction, RolePunishmentService(service.game), data["punishment"]
            )
            return
        information = data["information"]
        summary = (
            "Your Doll source: "
            + data["phase"]
            + ". Benefits: "
            + (", ".join(data["benefits"]) or "not selected")
            + "."
        )
        if information:
            summary += (
                " Actual question: "
                + (information["question"] or "none; secret offered")
                + ". Reply: "
                + (information["answer"] or "awaiting the original counterpart")
                + "."
            )
        if data["departure_account"]:
            summary += " Your actual departure: " + data["departure_account"] + "."
        if data["return_account"]:
            summary += " Your actual return: " + data["return_account"] + "."
        if not options:
            await reply(interaction, summary)
            return

        async def choose_control(
            current: discord.Interaction, values: dict[str, Any]
        ) -> str | None:
            leaving = values["operation"][0] == "leave"

            async def submit(response: discord.Interaction, answer: dict[str, Any]) -> str:
                method = service.game.depart_doll if leaving else service.game.return_doll
                await asyncio.to_thread(
                    method,
                    viewer_from_interaction(response),
                    str(response.id),
                    data["channel"],
                    data["leave"] if leaving else data["departure"],
                    data["revision"],
                    answer["account"],
                )
                return (
                    "Your actual scene departure is saved; broad map position was not changed."
                    if leaving
                    else "Your re-entry is saved; travel and body facts remain authoritative."
                )

            form = NativeForm(
                current.user.id,
                "Actual Doll departure" if leaving else "Actual factual re-entry",
                "Describe the actual scene event. The original body and map location "
                "remain authoritative; an OOC withdrawal is not a fictional exit.",
                [
                    Field(
                        "account",
                        "Your actual exit" if leaving else "Your actual return",
                        paragraph=True,
                    )
                ],
                submit,
            )
            await reply(current, form.text(), form)
            return None

        form = NativeForm(
            viewer.user_id,
            "Your saved Doll controls",
            summary,
            [Field("operation", "Optional actual scene control", tuple(options))],
            choose_control,
        )
        await reply(interaction, form.text(), form)
        return
    menu = await asyncio.to_thread(service.menu, viewer, channel)
    options = [("play", "Fade into the background with a genuine Play")] if menu["targets"] else []
    options.extend((x["id"], x["label"]) for x in menu["history"])
    if not options:
        await reply(
            interaction,
            "No supported current Doll source or private saved record here. "
            "Other Vatgrown rules remain separate workflows.",
        )
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        if values["source"][0] != "play":
            await open_vatgrown(current, service, values["source"][0])
            return None
        sheet = await asyncio.to_thread(service.game.sheet, viewer_from_interaction(current))
        identities = [
            x
            for x in sheet["identities"] + sheet.get("additional_identities", [])
            if not x["marked"]
        ]

        async def prepare(response: discord.Interaction, answer: dict[str, Any]) -> str:
            target = next(
                x
                for x in menu["targets"]
                if ActorRef.model_validate(x["ref"]).token == answer["target"][0]
            )
            result = await asyncio.to_thread(
                service.game.begin,
                viewer_from_interaction(response),
                str(response.id),
                channel,
                sheet["revision"],
                PlayInput(
                    play="unassuming_doll",
                    target_actor=ActorRef.model_validate(target["ref"]),
                    identity=answer["identity"][0] if answer.get("identity") else None,
                    gain=int(answer["gain"][0]),
                    heat=int(answer["heat"][0]),
                    context=answer["account"],
                    trigger_confirmed=True,
                ),
            )
            return "Actual Unassuming Doll Play prepared: " + str(result["action_id"])

        fields = [
            Field(
                "target",
                "Actual person who could notice or answer",
                tuple(
                    (ActorRef.model_validate(x["ref"]).token, x["label"]) for x in menu["targets"]
                ),
            ),
            Field(
                "identity",
                "Optional actual Identity to mark",
                tuple((x["id"], x["name"]) for x in identities),
                minimum=0,
                required=False,
            ),
            Field("gain", "Ordinary Identity Heat", tuple((str(x), str(x)) for x in range(4))),
            Field(
                "heat",
                "Actual Heat spent",
                tuple((str(x), str(x)) for x in range(sheet["heat"] + 4)),
            ),
            Field("account", "Your actual fading-into-background trigger", paragraph=True),
        ]
        form = NativeForm(
            current.user.id,
            "Unassuming Doll",
            "Use the original outside-Frame body and actual scene. "
            "All existing Heat/Identity spending rules apply.",
            fields,
            prepare,
        )
        await reply(current, form.text(), form)
        return None

    form = NativeForm(
        viewer.user_id,
        "Vatgrown: Unassuming Doll",
        "Original-source controls only; other Vatgrown abilities are not claimed complete.",
        [Field("source", "Your source control", tuple(options))],
        choose,
    )
    await reply(interaction, form.text(), form)
