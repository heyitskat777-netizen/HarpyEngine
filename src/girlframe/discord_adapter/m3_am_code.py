"""Actual circuit operator choices and original AM fulfillment; no authored player reply."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_state import ActorRef
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
    options += [
        ("document:" + x["id"], "Read learned record: " + x["label"]) for x in data["documents"]
    ]
    options += [
        ("memory:" + x["memory_erasure"], "Read original private memory effect")
        for x in data["sessions"]
        if x["memory_erasure"]
    ]
    options += [
        ("backup:" + x["id"], "Saved AM backup, revision " + str(x["captured_revision"]))
        for x in data["backups"]
    ]
    choices = await asyncio.to_thread(service.game.choices, viewer)
    options += [
        ("choice:" + x["id"], "Continue " + x["kind"].replace("_", " "))
        for x in choices
        if x["kind"].startswith("am_code_")
    ]
    if not options:
        await reply(interaction, "No current supported AM circuit-maintenance source.")
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        operation, identity = values["source"][0].split(":", 1)
        if operation == "backup":
            from girlframe.discord_adapter.m3_am_backup import open_backup
            from girlframe.services.m3_am_backup import BackupService

            await open_backup(current, BackupService(service.game), identity)
            return None
        if operation == "memory":
            from girlframe.discord_adapter.m3_am_memory import open_memory
            from girlframe.services.m3_am_memory import MemoryService

            await open_memory(current, MemoryService(service.game), identity)
            return None
        if operation == "document":
            from girlframe.discord_adapter.m3_am_records import open_document
            from girlframe.services.m3_am_records import RecordsService

            await open_document(current, RecordsService(service.game), identity)
            return None
        if operation == "choice":
            await open_choice(current, service.game, identity)
            return None

        session = next((x for x in data["sessions"] if x["id"] == identity), None)
        source_fields = [
            Field("account", "Your actual maintenance or factual circuit access", paragraph=True)
        ]
        if operation == "propose":
            source_fields.insert(
                0,
                Field(
                    "records_subject",
                    "Optional complete Foundation record request",
                    (("none", "Identity/memory maintenance only"),)
                    + tuple((x["token"], x["label"]) for x in data["subjects"]),
                ),
            )
        elif session and session["records"]:
            source_fields.extend(
                [
                    Field("reference", "Actual complete Foundation file/reference", paragraph=True),
                    Field(
                        "document",
                        "COMPLETE unredacted record (not a summary; max1200)",
                        paragraph=True,
                    ),
                    Field(
                        "complete",
                        "This is all genuinely recorded information",
                        (("yes", "Yes, complete and unredacted"),),
                    ),
                ]
            )

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
                    records_subject=next(
                        (
                            ActorRef.model_validate(x["ref"])
                            for x in data["subjects"]
                            if x["token"] == answer["records_subject"][0]
                        ),
                        None,
                    ),
                )
                return (
                    "Actual Identity/memory maintenance proposed; "
                    "the real operator confirms circuit access."
                )
            await asyncio.to_thread(
                service.confirm,
                human,
                str(actual.id),
                identity,
                data["revision"],
                answer["account"],
                records_document=answer.get("document"),
                records_reference=answer.get("reference"),
                records_complete=answer.get("complete") == ("yes",),
            )
            return (
                "Actual circuit access confirmed; "
                "the original AM owns preparation and the real roll."
            )

        form = NativeForm(
            current.user.id,
            "AM circuit access",
            (
                f"Prepare ALL Foundation records about {session['records_subject']}. "
                "Only the authenticated GM may attest completeness; "
                "do not summarize, truncate, or import private notes. "
                "If the complete file exceeds 1200 characters, this source is unavailable. "
                if session and session["records"]
                else ""
            )
            + "Confirm real physical access between these original bodies; "
            "Identity/memory maintenance. "
            "On low, only an actual spoken-statement Order is supported. "
            "A requested Foundation record must be genuine and complete before rolling. "
            "Body/branch operations and other Order effects remain unavailable.",
            source_fields,
            submit,
        )
        await reply(current, form.text(), form)
        return None

    form = NativeForm(
        viewer.user_id,
        "AM Identity/memory circuit maintenance",
        f"Original scene <#{channel}>. Only the actual already-knowing NPC can operate. "
        "New operator knowledge/body/vessel/branch ports remain unavailable.",
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
    if data["kind"].startswith("am_code_records_"):
        from girlframe.discord_adapter.m3_am_records import open_choice as open_records_choice

        await open_records_choice(interaction, game, identity)
        return
    if data["kind"] == "am_code_options":

        async def options(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                game.respond,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                ChoiceAnswer(options=tuple(values.get("options", ()))),
            )
            return "Actual printed selections saved; complete each selected source effect."

        form = NativeForm(
            interaction.user.id,
            "Operator: choose up to two",
            "Choose up to two supported printed options, or none. "
            "A backup freezes this actual moment before any selected rewrite. "
            "Records are learned by the operator; "
            "the AM receives no automatic transcript.",
            [
                Field(
                    "options",
                    "Actual printed options",
                    tuple(
                        (
                            x,
                            "Identity rewrite and/or memory erasure (one option)"
                            if x == "identities"
                            else "Genuine backup of all Identities and memories"
                            if x == "backup"
                            else "Complete Foundation records and one question",
                        )
                        for x in detail["available_options"]
                    ),
                    minimum=0,
                    maximum=min(2, len(detail["available_options"])),
                    required=False,
                )
            ],
            options,
        )
        await reply(interaction, form.text(), form)
        return
    if data["kind"] == "am_code_edit":

        async def select(current: discord.Interaction, values: dict[str, Any]) -> str | None:
            selected = tuple(values.get("identities", ()))
            available = {x["id"]: x for x in detail["identities"]}
            fields = [
                Field("identity_" + str(i), "Replace " + available[x]["name"])
                for i, x in enumerate(selected)
            ]
            scope = values.get("memory_scope", ("none",))[0]
            if scope == "selected":
                fields.append(
                    Field("memories", "Actual memories to erase (one per line)", paragraph=True)
                )
            fields.append(
                Field(
                    "account", "Your actual rewrite (zero replacements is allowed)", paragraph=True
                )
            )

            async def submit(actual: discord.Interaction, answer: dict[str, Any]) -> str:
                edits = {x: answer["identity_" + str(i)] for i, x in enumerate(selected)}
                edits["memory_scope"] = scope
                if scope == "selected":
                    edits["memories"] = answer["memories"]
                await asyncio.to_thread(
                    game.respond,
                    viewer_from_interaction(actual),
                    str(actual.id),
                    identity,
                    data["revision"],
                    ChoiceAnswer(options=("edit",), fields=edits, text=answer["account"]),
                )
                return (
                    "Actual Identity/memory effect saved. The original AM and operator can "
                    "recover its private memory record from circuit maintenance."
                )

            form = NativeForm(
                current.user.id,
                "Actual Identity/memory effect",
                "The actual operator chooses the new labels and memory loss. "
                "Memory erasure changes fictional recall and preserves OOC history. "
                "Limited, protected, Paired and source-locked Identities remain.",
                fields,
                submit,
            )
            await reply(current, form.text(), form)
            return None

        selection_fields = [
            Field(
                "memory_scope",
                "Erase original AM memories",
                (
                    ("none", "No memory erasure"),
                    ("selected", "Selected actual memories"),
                    ("all", "All memories held before this operation"),
                ),
            )
        ]
        if detail["identities"]:
            selection_fields.insert(
                0,
                Field(
                    "identities",
                    "Actual eligible original Identities",
                    tuple((x["id"], x["name"]) for x in detail["identities"]),
                    minimum=0,
                    maximum=min(4, len(detail["identities"])),
                    required=False,
                ),
            )
        form = NativeForm(
            interaction.user.id,
            "Operator: Just Code",
            "Select actual non-Limited Identities to rewrite, or none, and any memory erasure. "
            "Both together consume this single printed option. "
            "On high, this already-knowing operator also causes actual Status loss.",
            selection_fields,
            select,
            values={"memory_scope": ("none",)},
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
