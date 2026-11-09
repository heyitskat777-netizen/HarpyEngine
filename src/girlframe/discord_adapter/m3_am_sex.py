"""Private AM counterpart-Play and real circuit-maintenance navigation."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_memory_pages import MemoryForm, MemoryHistory
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_am_sex import SexService
from girlframe.services.onboarding import WorkflowError


async def open_am_sex(
    interaction: discord.Interaction,
    service: SexService,
    *,
    bonded_source: str | None = None,
    learned_source: str | None = None,
    identity: str | None = None,
) -> None:
    if learned_source is not None or identity is not None:
        if bonded_source is not None:
            raise WorkflowError("Keep actual learned and Bonded sources separate")
        await _open_learned(interaction, service, identity, learned_source)
        return
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(
        service.menu, viewer, int(interaction.channel_id or 0), bonded_source=bonded_source
    )
    options = (
        [("circuits", "Actual circuit contact: use Just Code")] if bonded_source is None else []
    )
    options += [
        (x["id"], x["play"].replace("_", " ") + " · " + x["state"]) for x in data["sources"]
    ]

    if not options:
        await reply(
            interaction,
            "Your actual counterpart opens and confirms their own genuine Sex source. "
            "This copied AM rule adds no roll, Heat, Identity mark or circuit hardware. "
            "Reopen when that actual source exists.",
        )
        return

    async def select(current: discord.Interaction, values: dict[str, Any]) -> None:
        source = values["source"][0]
        if source == "circuits":
            from girlframe.discord_adapter.m3_am_code import open_code
            from girlframe.services.m3_am_code import CodeService

            await open_code(current, CodeService(service.game))
            return
        fresh = await asyncio.to_thread(
            service.menu,
            viewer_from_interaction(current),
            data["channel"],
            bonded_source=bonded_source,
        )
        actual = next((x for x in fresh["sources"] if x["id"] == source), None)
        if actual is None:
            raise WorkflowError("Reopen the actual original counterpart source")
        if bonded_source is not None:
            await asyncio.to_thread(
                service.bind_source,
                viewer_from_interaction(current),
                str(current.id),
                bonded_source,
                actual["id"],
            )
        if actual["choices"]:
            from girlframe.discord_adapter.m2_ui import open_choice

            await open_choice(current, service.game, actual["choices"][0])
        else:
            await reply(
                current,
                "Counterpart source `"
                + actual["id"]
                + "` · "
                + actual["state"]
                + (
                    " · receipt `" + actual["receipt"] + "`"
                    if actual["receipt"]
                    else " · awaiting its actual roll"
                )
                + ". AM makes no additional Sex roll. Original source owners retain their choices.",
            )

    form = NativeForm(
        viewer.user_id,
        "AM: counterpart source",
        (
            "Your counterpart uses their own genuine Sex Play after its actual "
            "voluntary source confirmation. "
            "AM makes no additional Sex roll, marks no extra Identity "
            "and spends no extra Heat here. "
            + (
                "If someone actually accesses your circuits, use the existing Just Code controls "
                "and its separate source confirmation. "
                if bonded_source is None
                else "Borrowing AM Sex grants no AM circuit hardware. "
            )
            + "This card does not grant circuit access or make a choice for either player."
        ),
        [Field("source", "Open actual source", tuple(options))],
        select,
    )
    await reply(interaction, form.text(), form)


async def _open_learned(
    interaction: discord.Interaction,
    service: SexService,
    identity: str | None,
    lesson: str | None,
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity is None:
        data = await asyncio.to_thread(
            service.lesson_menu, viewer, int(interaction.channel_id or 0), lesson
        )
        options = [(x["id"], x["label"]) for x in data["tasks"]]
        if data["targets"]:
            options.insert(0, ("invite", "Propose one actual voluntary no-roll source"))
        if not options:
            await reply(
                interaction, "No actual unused AM lesson or private saved source is available."
            )
            return

        async def choose(current: discord.Interaction, values: dict[str, Any]) -> None:
            selected = values["source"][0]
            if selected != "invite":
                await _open_learned(current, service, selected, None)
                return

            async def invite(response: discord.Interaction, answers: dict[str, Any]) -> str:
                actual = next(x for x in data["targets"] if x["id"] == answers["target"][0])
                result = await asyncio.to_thread(
                    service.invite,
                    viewer_from_interaction(response),
                    str(response.id),
                    data["channel"],
                    ActorRef.model_validate(actual["ref"]),
                    data["revision"],
                    answers["account"],
                    learned_source=answers["lesson"][0],
                )
                return (
                    "Actual no-roll source proposed: "
                    + str(result["id"])
                    + ". The original counterpart answers independently."
                )

            form = NativeForm(
                current.user.id,
                "Actual learned AM invitation",
                "This reserves your one-use lesson, not another person's consent. "
                "Both people author "
                "their own performed scene later. No circuit hardware or Just Code is granted.",
                [
                    Field(
                        "target",
                        "Actual original counterpart",
                        tuple((x["id"], x["label"]) for x in data["targets"]),
                    ),
                    Field(
                        "lesson",
                        "One actual no-roll lesson",
                        tuple((x["id"], x["label"]) for x in data["lessons"]),
                    ),
                    Field("account", "Your actual voluntary proposal", paragraph=True),
                ],
                invite,
            )
            await reply(current, form.text(), form)

        form = NativeForm(
            viewer.user_id,
            "Learned AM no-roll source",
            "No extra Action, dice, Heat or circuit capability is created.",
            [Field("source", "Your actual source", tuple(options))],
            choose,
        )
        await reply(interaction, form.text(), form)
        return
    data = await asyncio.to_thread(service.view_learned, viewer, identity)
    body = data["body"]
    summary = (
        "Actual learned AM source: "
        + body["phase"]
        + ". "
        + (
            "One use spent by its real performed/known source."
            if body["used_event"]
            else "Unused source reservation."
        )
        + " No additional Action, roll, Heat or circuit access.\n\n"
        + clean(body["account"])
    )
    for item in data["performances"]:
        summary += (
            "\n\nActual original participant "
            + str(item["controller"])
            + ": "
            + clean(item["account"])
        )
    for gift in data["unrolled_gender"]:
        summary += "\n\nMandatory Animal Tag " + (
            "given: " + clean(gift["tag_label"] or "") if gift["tag"] else "still owed."
        )

    async def authorize(current: discord.Interaction) -> None:
        await asyncio.to_thread(service.view_learned, viewer_from_interaction(current), identity)

    pending = [x for x in data["unrolled_gender"] if x["pending"]]
    options = []
    if data["can_confirm"]:
        options.append(("confirm", "Your own voluntary source response"))
    if data["actions"]:
        options.append(("bind", "Bind genuine counterpart receipt/source"))
    if data["can_perform"]:
        options.append(("perform", "Record your own actually performed scene"))
    if data["can_complete"]:
        options.append(("complete", "Verify actual finished counterpart work"))
    if pending:
        options.append(("gift", "Give your real mandatory Animal Tag"))
    if data["can_withdraw"]:
        options.append(("withdraw", "Withdraw unused voluntary source"))
    if not options:
        view = MemoryHistory(viewer.user_id, summary, authorize)
        await reply(interaction, view.text(), view)
        return

    async def select(current: discord.Interaction, values: dict[str, Any]) -> None:
        operation = values["operation"][0]
        fresh = await asyncio.to_thread(
            service.view_learned, viewer_from_interaction(current), identity
        )
        fields = [Field("account", "Your actual original-person account", paragraph=True)]
        if operation == "confirm":
            fields.insert(
                0,
                Field(
                    "accept",
                    "Your actual voluntary answer",
                    (("yes", "Confirm"), ("no", "Decline")),
                ),
            )
        elif operation == "perform":
            fields.insert(
                0,
                Field(
                    "circuits",
                    "This actual scene does not manipulate circuits",
                    (("no", "No circuit manipulation"),),
                ),
            )
        elif operation == "bind":
            fields = [
                Field(
                    "action",
                    "Actual independently rolled counterpart source",
                    tuple((x["id"], x["label"]) for x in fresh["actions"]),
                )
            ]
        elif operation == "gift":
            fields = [
                Field(
                    "gift",
                    "Your actual mandatory gift",
                    tuple(
                        (x["id"], "Original non-Animal counterpart")
                        for x in fresh["unrolled_gender"]
                        if x["pending"]
                    ),
                ),
                Field("tag", "Your actual Tag", paragraph=True),
            ]

        async def submit(response: discord.Interaction, answers: dict[str, Any]) -> str:
            who, key = viewer_from_interaction(response), str(response.id)
            if operation == "confirm":
                await asyncio.to_thread(
                    service.confirm,
                    who,
                    key,
                    identity,
                    fresh["revision"],
                    answers["accept"][0] == "yes",
                    answers["account"],
                )
            elif operation == "perform":
                await asyncio.to_thread(
                    service.perform,
                    who,
                    key,
                    identity,
                    fresh["revision"],
                    answers["account"],
                    circuits_touched=answers["circuits"][0] != "no",
                )
            elif operation == "bind":
                await asyncio.to_thread(
                    service.bind_counterpart,
                    who,
                    key,
                    identity,
                    fresh["revision"],
                    answers["action"][0],
                )
            elif operation == "gift":
                from girlframe.services.p1_unrolled_sex import give

                await asyncio.to_thread(
                    give,
                    service.game,
                    who,
                    key,
                    answers["gift"][0],
                    fresh["revision"],
                    answers["tag"],
                )
            else:
                method = service.withdraw if operation == "withdraw" else service.complete
                await asyncio.to_thread(
                    method, who, key, identity, fresh["revision"], answers["account"]
                )
            return (
                "Your actual owned source response is saved. "
                "Pending performances/gifts retain their controls."
            )

        form = MemoryForm(
            current.user.id,
            "Your actual learned AM " + operation,
            summary,
            fields,
            submit,
            authorize=authorize,
        )
        await reply(current, form.text(), form)

    form = MemoryForm(
        viewer.user_id,
        "Learned AM source controls",
        summary,
        [Field("operation", "Your actual source control", tuple(options))],
        select,
        authorize=authorize,
    )
    await reply(interaction, form.text(), form)
