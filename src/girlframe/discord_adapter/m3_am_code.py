"""Actual circuit operator choices and original AM fulfillment; no authored player reply."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.services.m2_game import GameService
from girlframe.services.m3_am_code import CodeService


async def open_source(
    interaction: discord.Interaction, service: CodeService, identity: str
) -> None:
    channel = await asyncio.to_thread(
        service.source_channel, viewer_from_interaction(interaction), identity
    )
    await open_code(interaction, service, channel=channel)


async def open_code(
    interaction: discord.Interaction, service: CodeService, *, channel: int | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    channel = channel if channel is not None else int(interaction.channel_id or 0)
    data = await asyncio.to_thread(service.menu, viewer, channel)
    options = [("propose:" + x["id"], "Maintain with " + x["label"]) for x in data["known"]]
    options += [
        ("confirm:" + x["id"], "Confirm actual circuit access")
        for x in data["sessions"]
        if x["phase"] == "proposed" and x["controller"] == viewer.user_id
    ]
    choices = await asyncio.to_thread(service.game.choices, viewer)
    options += [
        ("choice:" + x["id"], "Continue " + x["kind"].replace("_", " "))
        for x in choices
        if x["kind"].startswith("am_code_")
    ]
    if not options:
        await reply(interaction, "No current supported identity-only AM maintenance source.")
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        operation, identity = values["source"][0].split(":", 1)
        if operation == "choice":
            await open_choice(current, service.game, identity)
            return None

        async def submit(actual: discord.Interaction, answer: dict[str, Any]) -> str:
            human = viewer_from_interaction(actual)
            if operation == "propose":
                await asyncio.to_thread(
                    service.propose,
                    human,
                    str(actual.id),
                    identity,
                    data["revision"],
                    answer["account"],
                )
                return (
                    "Actual identity-only maintenance proposed; "
                    "the real operator confirms circuit access."
                )
            await asyncio.to_thread(
                service.confirm,
                human,
                str(actual.id),
                identity,
                data["revision"],
                answer["account"],
            )
            return (
                "Actual circuit access confirmed; "
                "the original AM owns preparation and the real roll."
            )

        form = NativeForm(
            current.user.id,
            "AM circuit access",
            "Confirm real physical access between these original bodies; "
            "identity-only maintenance. "
            "On low, only an actual spoken-statement Order is supported. "
            "Memory/body/backup/record operations and other Order effects are unavailable.",
            [Field("account", "Your actual maintenance or factual circuit access", paragraph=True)],
            submit,
        )
        await reply(current, form.text(), form)
        return None

    form = NativeForm(
        viewer.user_id,
        "AM identity-only circuit maintenance",
        f"Original scene <#{channel}>. Only the actual already-knowing NPC can operate. "
        "New knowledge/body/vessel/backup/memory/record ports remain unavailable.",
        [Field("source", "Actual source or owned response", tuple(options))],
        choose,
    )
    await reply(interaction, form.text(), form)


async def open_choice(interaction: discord.Interaction, game: GameService, identity: str) -> None:
    data = await asyncio.to_thread(game.decision, viewer_from_interaction(interaction), identity)
    detail = data["am_code"]
    if data["kind"] == "am_code_prepare":
        from girlframe.discord_adapter.m2_ui import open_play

        await open_play(interaction, game, parent=data)
        return
    if data["kind"] == "am_code_edit":

        async def select(current: discord.Interaction, values: dict[str, Any]) -> str | None:
            selected = tuple(values.get("identities", ()))
            available = {x["id"]: x for x in detail["identities"]}
            fields = [
                Field("identity_" + str(i), "Replace " + available[x]["name"])
                for i, x in enumerate(selected)
            ]
            fields.append(
                Field(
                    "account", "Your actual rewrite (zero replacements is allowed)", paragraph=True
                )
            )

            async def submit(actual: discord.Interaction, answer: dict[str, Any]) -> str:
                edits = {x: answer["identity_" + str(i)] for i, x in enumerate(selected)}
                await asyncio.to_thread(
                    game.respond,
                    viewer_from_interaction(actual),
                    str(actual.id),
                    identity,
                    data["revision"],
                    ChoiceAnswer(options=("edit",), fields=edits, text=answer["account"]),
                )
                return (
                    "Actual source rewrite saved; original marks, slots, body and hardware remain."
                )

            form = NativeForm(
                current.user.id,
                "Actual Identity rewrite",
                "Choose the actual new labels. Limited, protected, Paired "
                "and source-locked identities remain.",
                fields,
                submit,
            )
            await reply(current, form.text(), form)
            return None

        if not detail["identities"]:
            await select(interaction, {"identities": ()})
            return
        form = NativeForm(
            interaction.user.id,
            "Operator: Just Code",
            "Select actual non-Limited identities to rewrite, or none. "
            "On high, this already-knowing operator also causes actual Status loss.",
            [
                Field(
                    "identities",
                    "Actual eligible original Identities",
                    tuple((x["id"], x["name"]) for x in detail["identities"]),
                    minimum=0,
                    maximum=min(4, len(detail["identities"])),
                    required=False,
                )
            ],
            select,
        )
    else:
        fields = []
        if data["kind"] == "am_code_obey":
            fields.append(
                Field(
                    "behavior",
                    "Your actual way of following",
                    tuple((x, x.replace("_", " ").title()) for x in detail["behavior"]),
                )
            )
        fields.append(
            Field(
                "account",
                "Actual words the original AM must say"
                if data["kind"] == "am_code_order"
                else "Your own actual matching spoken words",
                paragraph=True,
            )
        )

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                game.respond,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                ChoiceAnswer(options=tuple(values.get("behavior", ())), text=values["account"]),
            )
            if data["kind"] == "am_code_obey":
                return (
                    "Your actual spoken statement is saved; the Order and maintenance are complete."
                )
            return "The real Order is saved; the original AM owns her actual spoken performance."

        form = NativeForm(
            interaction.user.id,
            "Just Code: original owned Order",
            detail["instruction"]
            or "The actual operator gives the original AM a real irresistible Order.",
            fields,
            submit,
        )
    await reply(interaction, form.text(), form)
