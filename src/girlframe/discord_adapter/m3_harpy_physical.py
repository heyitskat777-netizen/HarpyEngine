"""Private actual Harpy Frame consent and source-owned extraction/medical proposals."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_harpy_physical import HarpyPhysicalService


async def open_physical(
    interaction: discord.Interaction, service: HarpyPhysicalService, actor: ActorRef
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), actor)
    options: list[tuple[str, str]] = []
    if data["owner"] and data["locked"]:
        options.extend(
            (
                ("allow", "Frame: allow actual extraction"),
                ("refuse", "Frame: refuse or revoke extraction"),
                ("open", "Frame: open this actual cockpit"),
            )
        )
    if data["linked"] and data["extractors"]:
        options.append(("extract", "Propose your actual extraction assistance"))
    if data["owner"] and not data["linked"] and (not data["vitals"] or data["incapacitated"]):
        options.append(("recover", "Request real medical help for this body"))
    if not options:
        await reply(
            interaction,
            "The actual Frame voice or a source-scene participant must supply the next step.",
        )
        return

    async def choose(current: discord.Interaction, operation: str) -> None:
        fields = []
        if operation == "extract":
            fields.append(
                Field(
                    "extractor",
                    "Your actual source-scene role",
                    tuple((x["token"], x["label"]) for x in data["extractors"]),
                )
            )
        fields.append(
            Field("account", "Describe your actual physical action or help", paragraph=True)
        )

        async def submit(response: discord.Interaction, values: dict[str, Any]) -> str:
            if operation in ("allow", "refuse", "open"):
                await asyncio.to_thread(
                    service.voice,
                    viewer_from_interaction(response),
                    str(response.id),
                    actor,
                    data["expected"],
                    operation,
                    values["account"],
                )
                return (
                    "The actual Frame's explicit response is saved. "
                    "Consent does not extract or revive the body."
                )
            extractor = next(
                (
                    ActorRef.model_validate(x["ref"])
                    for x in data["extractors"]
                    if operation == "extract" and x["token"] == values["extractor"][0]
                ),
                None,
            )
            result = await asyncio.to_thread(
                service.propose,
                viewer_from_interaction(response),
                str(response.id),
                actor,
                data["expected"],
                operation,
                values["account"],
                extractor=extractor,
            )
            return "Your actual source-owned help awaits human GM factual review: " + str(
                result["id"]
            )

        form = NativeForm(
            current.user.id,
            "Actual Harpy physical response",
            "No transport, healing, new resources or consent is inferred.",
            fields,
            submit,
        )
        await reply(current, form.text(), form)

    await Picker(interaction.user.id, "Actual Harpy Frame and body", tuple(options), choose).show(
        interaction
    )


async def open_review(
    interaction: discord.Interaction, service: HarpyPhysicalService, identity: str
) -> None:
    data = await asyncio.to_thread(service.review, viewer_from_interaction(interaction), identity)
    if data["state"] == "resolved" or not data["can_review"]:
        await reply(
            interaction,
            "This actual help request awaits its original human GM or is already reviewed.",
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.confirm,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            accepted=values["accept"][0] == "yes",
            evidence=values["evidence"],
        )
        return "Your actual factual review is saved; only the established physical flags change."

    form = NativeForm(
        interaction.user.id,
        "Review actual Harpy help",
        data["body"]["account"],
        [
            Field(
                "accept",
                "Has this real help occurred with actual access?",
                (("yes", "Yes; apply this actual help"), ("no", "No; decline this proposal")),
            ),
            Field("evidence", "Record actual contact or medical help", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
