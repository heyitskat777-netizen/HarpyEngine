"""Actual comparison authors own optional Tags; owner disclosure is addressed and private."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field
from girlframe.discord_adapter.m3_memory_pages import MemoryForm, MemoryHistory
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_vatgrown_dna import VatgrownDNAService
from girlframe.services.onboarding import WorkflowError


async def open_vatgrown_dna(
    interaction: discord.Interaction, service: VatgrownDNAService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity is not None:
        shown = await asyncio.to_thread(service.view, viewer, identity)

        async def access(current: discord.Interaction) -> None:
            await asyncio.to_thread(service.view, viewer_from_interaction(current), identity)

        lines = ["**Your actual DNA source**"]
        for name in (
            "vatgrown",
            "recipient",
            "comparer",
            "basis",
            "account",
            "outcome",
            "label",
            "resolution_account",
        ):
            if shown.get(name) is not None:
                lines.append(clean(name.replace("_", " ")) + ": " + clean(shown[name]))
        text = "\n".join(lines)
        if not shown.get("can_resolve"):
            history = MemoryHistory(viewer.user_id, text, access)
            await reply(interaction, history.text(), history)
            return

        async def settle(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.resolve,
                viewer_from_interaction(current),
                str(current.id),
                shown["revision"],
                identity,
                values.get("tag", "") if values["choice"] == ("give",) else None,
                values["account"],
            )
            return "Your optional first-comparison Tag choice is saved once."

        form = MemoryForm(
            viewer.user_id,
            "Your first-comparison choice",
            text,
            [
                Field(
                    "choice",
                    "Actual comparer choice",
                    (("give", "Give your Tag"), ("decline", "Decline the Tag")),
                ),
                Field("tag", "Your Tag if giving one", required=False),
                Field("account", "Your actual choice account", paragraph=True),
            ],
            settle,
            authorize=access,
        )
        await reply(interaction, form.text(), form)
        return
    channel = int(interaction.channel_id or 0)
    menu = await asyncio.to_thread(service.menu, viewer, channel)
    options = [("history:" + task["id"], task["label"]) for task in menu["tasks"]]
    if menu["roles"] and menu["targets"]:
        options.append(("compare", "Record your actual first comparison"))
    if menu["own_basis"]:
        options.append(("basis", "Read your own private DNA basis"))
        if menu["recipients"]:
            options.append(("disclose", "Disclose your basis to one actual recipient"))

    async def access_menu(current: discord.Interaction) -> None:
        await asyncio.to_thread(service.menu, viewer_from_interaction(current), channel)

    if not options:
        await reply(interaction, "No owned saved DNA source or actual joined comparison roles.")
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        token = values["entry"][0]
        if token.startswith("history:"):
            await open_vatgrown_dna(current, service, token.removeprefix("history:"))
            return None
        if token == "basis":
            history = MemoryHistory(
                viewer.user_id,
                "\n".join(clean(row["basis"]) for row in menu["own_basis"]),
                access_menu,
            )
            await reply(current, history.text(), history)
            return None
        if token == "compare":
            actors = {row["id"]: row for row in menu["roles"]}
            targets = {row["id"]: row for row in menu["targets"]}

            async def compare(response: discord.Interaction, answers: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.compare,
                    viewer_from_interaction(response),
                    str(response.id),
                    menu["revision"],
                    channel,
                    ActorRef.model_validate(targets[answers["target"][0]]["actor"]),
                    ActorRef.model_validate(actors[answers["comparer"][0]]["actor"]),
                    answers["account"],
                )
                return (
                    "Your actual first comparison is saved. "
                    "Reopen DNA controls to give or decline your Tag."
                )

            form = MemoryForm(
                viewer.user_id,
                "Actual comparison",
                "Record the first actual comparison this campaign between this Vatgrown "
                "and their saved DNA basis person. This does not disclose the private basis "
                "or infer resemblance. Owner disclosure is optional.",
                [
                    Field(
                        "comparer",
                        "Your actual comparer role",
                        tuple((key, row["label"]) for key, row in actors.items()),
                    ),
                    Field(
                        "target",
                        "Actual Vatgrown",
                        tuple((key, row["label"]) for key, row in targets.items()),
                    ),
                    Field("account", "Your actual performed comparison", paragraph=True),
                ],
                compare,
                authorize=access_menu,
            )
        elif token == "disclose":
            actors = {str(index): row for index, row in enumerate(menu["own_basis"])}
            recipients = {row["id"]: row for row in menu["recipients"]}

            async def disclose(response: discord.Interaction, answers: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.disclose,
                    viewer_from_interaction(response),
                    str(response.id),
                    menu["revision"],
                    channel,
                    ActorRef.model_validate(actors[answers["owner"][0]]["actor"]),
                    ActorRef.model_validate(recipients[answers["recipient"][0]]["actor"]),
                    answers["account"],
                )
                return "Your private basis was shared with that actual addressed recipient."

            form = MemoryForm(
                viewer.user_id,
                "Addressed DNA disclosure",
                "Share your exact saved basis only with this actual recipient. "
                "This does not perform a comparison.",
                [
                    Field(
                        "owner",
                        "Your original source",
                        tuple((key, "Your saved DNA basis") for key in actors),
                    ),
                    Field(
                        "recipient",
                        "Actual recipient",
                        tuple((key, row["label"]) for key, row in recipients.items()),
                    ),
                    Field("account", "Your actual disclosure account", paragraph=True),
                ],
                disclose,
                authorize=access_menu,
            )
        else:
            raise WorkflowError("Choose your own actual DNA source controls")
        await reply(current, form.text(), form)
        return None

    form = MemoryForm(
        viewer.user_id,
        "Vatgrown DNA",
        "Actual comparisons and private addressed sources."
        + ("\n" + "\n".join(menu["gaps"]) if menu["gaps"] else ""),
        [Field("entry", "Your source controls", tuple(options))],
        choose,
        authorize=access_menu,
    )
    await reply(interaction, form.text(), form)
