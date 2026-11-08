"""Private original-owner controls for an actual mandatory rejection Play."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_memory_pages import MemoryForm, MemoryHistory
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_bonded_rejection as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_bonded_rejection import BondedRejectionService
from girlframe.services.onboarding import WorkflowError


async def open_bonded_rejection(
    interaction: discord.Interaction,
    service: BondedRejectionService,
    identity: str | None = None,
    *,
    account: str | None = None,
) -> None:
    viewer = viewer_from_interaction(interaction)
    menu = await asyncio.to_thread(service.menu, viewer)
    source = next((x for x in menu["sources"] if x["id"] == identity), None)
    if identity is None:
        options = [(x["id"], "Declare an actual mandatory rejection Play") for x in menu["sources"]]
        options += [(x["id"], x["label"]) for x in menu["history"]]
        if not options:
            await reply(interaction, "No actual source-owned mandatory rejection Play is pending.")
            return

        async def pick(response: discord.Interaction, values: dict[str, Any]) -> None:
            await open_bonded_rejection(response, service, values["source"][0])

        await NativeForm(
            interaction.user.id,
            "Actual rejection Plays",
            "Your original sources and private history.",
            [Field("source", "Actual source", tuple(options))],
            pick,
        ).present(interaction)
        return
    if source is not None:

        async def declare(response: discord.Interaction, values: dict[str, Any]) -> None:
            selected = next(
                (x for x in source["targets"] if x["token"] in values.get("target", ())), None
            )
            result = await asyncio.to_thread(
                service.request,
                viewer_from_interaction(response),
                str(response.id),
                source["id"],
                menu["revision"],
                values["play"][0],
                account if account is not None else values["account"],
                target=ActorRef.model_validate(selected["ref"]) if selected else None,
            )
            await open_bonded_rejection(response, service, result["id"])

        fields = [
            Field(
                "play",
                "Actual required Play (its own trigger must be true)",
                tuple(rules.PLAYS.items()),
            )
        ]
        if account is None:
            fields.append(
                Field(
                    "account",
                    "Your actual action rejecting the Tag and its real Play trigger",
                    paragraph=True,
                )
            )
        if source["targets"]:
            fields.append(
                Field(
                    "target",
                    "If targeted: actual original scene role",
                    tuple((x["token"], x["label"]) for x in source["targets"]),
                    minimum=0,
                    required=False,
                )
            )
        await NativeForm(
            interaction.user.id,
            "Declare your actual rejection action",
            "This records a real required Play context. Preparing does not perform the action. "
            "Only choose a Play whose ordinary trigger is actually true.",
            fields,
            declare,
        ).present(interaction)
        return

    data = await asyncio.to_thread(service.view, viewer, identity)

    async def authorize(current: discord.Interaction) -> None:
        await asyncio.to_thread(service.view, viewer_from_interaction(current), identity)

    summary = rules.PLAYS[data["play"]] + ": " + data["account"]
    last = data["attempts"][-1] if data["attempts"] else None
    for attempt in data["attempts"]:
        summary += "\nActual attempt " + attempt["action"] + ": " + attempt["state"]
        if attempt["released"]:
            summary += " · genuinely cancelled unrolled"
        if attempt["receipt"]:
            summary += " · real dice " + str(attempt["receipt"].get("faces", "recorded"))
        if attempt["finding"]:
            summary += (
                "\nOwner outcome: "
                + ("rejected" if attempt["finding"]["achieved"] else "still owed")
                + " · "
                + attempt["finding"]["account"]
            )
    options = []
    if data["can_start"]:
        options.append(("start", "Prepare your actual Play with real resources"))
    if data["can_conclude"]:
        options.append(("conclude", "Your factual outcome of the completed action"))
    if (
        last
        and not last["released"]
        and not last["finding"]
        and viewer.user_id == int(data["actor"]["entity"])
    ):
        options.append(
            (
                "recover" if last["recoverable"] else "resume",
                "Recover actual interrupted Play"
                if last["recoverable"]
                else "Resume real roll / required choices",
            )
        )
    if not options:
        history = MemoryHistory(
            interaction.user.id,
            clean(summary + "\nActual source work is waiting or resolved."),
            authorize,
        )
        await reply(interaction, history.text(), history)
        return

    async def operate(response: discord.Interaction, values: dict[str, Any]) -> None:
        operation = values["operation"][0]
        if operation == "start":
            from girlframe.discord_adapter.m2_ui import open_play

            await open_play(response, service.game, parent=data["descriptor"], _pilot=True)
        elif operation == "resume":
            from girlframe.discord_adapter.m2_ui import open_pending

            await open_pending(response, service.game)
        elif operation == "recover":
            from girlframe.discord_adapter.m3_recovery import open_recovery
            from girlframe.services.m3_recovery import RecoveryService

            saved = await asyncio.to_thread(
                RecoveryService(service.game).saved, viewer_from_interaction(response)
            )
            actual = next((x for x in saved if last and x["id"] == last["action"]), None)
            if actual is None:
                raise WorkflowError(
                    "Reopen the actual interrupted source after staff restores chat"
                )
            await open_recovery(response, service.game, actual)
        else:

            async def conclude(current: discord.Interaction, fields: dict[str, Any]) -> str:
                assert last is not None
                await asyncio.to_thread(
                    service.conclude,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    data["revision"],
                    last["id"],
                    fields["achieved"][0] == "yes",
                    fields["account"],
                )
                return (
                    "Your actual outcome is saved. Resume the original source or still-owed action."
                )

            await MemoryForm(
                response.user.id,
                "Your actual completed-action outcome",
                clean(summary),
                [
                    Field(
                        "achieved",
                        "Did your actual completed action reject this Tag?",
                        (
                            ("yes", "Yes: the performed action actually rejected it"),
                            ("no", "No: the Tag and rejection remain owed"),
                        ),
                    ),
                    Field("account", "Your factual action and actual outcome", paragraph=True),
                ],
                conclude,
                authorize=authorize,
            ).present(response)

    await MemoryForm(
        interaction.user.id,
        "Actual rejection Play",
        clean(summary),
        [Field("operation", "Your actual source controls", tuple(options))],
        operate,
        authorize=authorize,
    ).present(interaction)
