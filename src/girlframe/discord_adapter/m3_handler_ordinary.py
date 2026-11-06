"""Real human Session boundaries, scoped disclosure and useful-Identity award controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_handler_ordinary import HandlerOrdinaryService
from girlframe.services.onboarding import WorkflowError


async def open_ordinary(
    interaction: discord.Interaction, service: HandlerOrdinaryService, identity: str | None = None
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), identity)
    if data["kind"] == "review":
        if data["phase"] == "disclosure" and data["own"]:

            async def disclose(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.disclose,
                    viewer_from_interaction(current),
                    str(current.id),
                    data["id"],
                    data["revision"],
                    values["share"][0] == "yes",
                    values["account"],
                )
                return "Scoped disclosure saved. No advancement is granted by disclosure itself."

            await NativeForm(
                interaction.user.id,
                "Your actual replacement Identity disclosure",
                "Share these proved replacements with the original Handler for usefulness review: "
                + ", ".join(clean(x["name"]) for x in data["identities"]),
                [
                    Field(
                        "share",
                        "Share these actual replacements?",
                        (("yes", "Share for this review"), ("no", "Decline disclosure")),
                    ),
                    Field("account", "Your actual disclosure decision", paragraph=True),
                ],
                disclose,
            ).present(interaction)
            return
        if data["phase"] == "usefulness" and not data["own"]:

            async def judge(current: discord.Interaction, values: dict[str, Any]) -> str:
                reasons = {x["id"]: values["reason:" + x["id"]] for x in data["identities"]}
                await asyncio.to_thread(
                    service.grant_identity_award,
                    viewer_from_interaction(current),
                    str(current.id),
                    data["id"],
                    data["revision"],
                    reasons,
                    values["account"],
                )
                return "One ordinary Handler advancement is held. Open advancements to spend it."

            await NativeForm(
                interaction.user.id,
                "Judge actual replacements useful",
                "All starting Identities were legally replaced. Judge each disclosed replacement "
                "useful "
                "to your original Handler. This uses the current ordinary Session slot "
                "and permanently marks this criterion off.",
                [
                    Field("reason:" + x["id"], "Why is " + x["name"] + " useful?", paragraph=True)
                    for x in data["identities"]
                ]
                + [Field("account", "Actual usefulness accomplishment", paragraph=True)],
                judge,
            ).present(interaction)
            return
        await reply(
            interaction,
            "Starting Identity review — " + data["phase"] + ". Its actual source history is saved.",
        )
        return
    if not data["facilitator"]:
        await reply(
            interaction,
            "The authorized human facilitator records actual campaign Session boundaries. "
            "Use your requests for owned Identity review decisions.",
        )
        return
    selected = data.get("selected") or data.get("active")
    if selected and selected["end_event"]:
        await reply(
            interaction,
            "Actual Session ended: "
            + clean(selected["name"])
            + ". Ending a Session grants no advancement and does not reset criterion mark-off.",
        )
        return
    if selected:

        async def operate(current: discord.Interaction, values: dict[str, Any]) -> str:
            if values["operation"][0] == "end":
                await asyncio.to_thread(
                    service.end_session,
                    viewer_from_interaction(current),
                    str(current.id),
                    selected["id"],
                    data["revision"],
                    values["account"],
                )
                return "Actual Session end recorded by its facilitator. This grants no award."
            if not values.get("girl"):
                raise WorkflowError("Select the actual original Girl for the review")
            girl = next(x for x in data["girls"] if x["token"] == values["girl"][0])
            await asyncio.to_thread(
                service.request_review,
                viewer_from_interaction(current),
                str(current.id),
                selected["id"],
                data["revision"],
                ActorRef.model_validate(girl["actor"]),
                values["account"],
            )
            return "Actual replacement provenance verified. The original Girl controls disclosure."

        await NativeForm(
            interaction.user.id,
            "Actual campaign Session — " + selected["name"],
            "This OOC Session is distinct from scenes and Off-Duty. Actual replacements may come "
            "from earlier sessions. A boundary record grants no advancement.",
            [
                Field(
                    "operation",
                    "Actual Session operation",
                    (
                        ("review", "Request useful starting-Identity review"),
                        ("end", "Record actual Session end"),
                    ),
                ),
                Field(
                    "girl",
                    "Original Girl (review only)",
                    tuple((x["token"], x["label"]) for x in data["girls"]),
                    0,
                    1,
                    required=False,
                ),
                Field("account", "Actual source account", paragraph=True),
            ],
            operate,
        ).present(interaction)
        return

    async def start(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.record_session,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            values["name"],
            values["account"],
        )
        return (
            "Actual campaign Session recorded. Attendance and scenes do not create an advancement."
        )

    await NativeForm(
        interaction.user.id,
        "Record actual campaign Session start",
        "Record a real OOC campaign play Session as its authorized human facilitator. "
        "Session boundaries are separate from scenes, missions and Off-Duty. "
        "Starting grants no reward.",
        [
            Field("name", "Actual Session name"),
            Field(
                "actual", "Actual boundary", (("began", "This actual campaign Session has begun"),)
            ),
            Field("account", "Actual Session start account", paragraph=True),
        ],
        start,
    ).present(interaction)
