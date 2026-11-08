"""Actual self, bonded-Girl and Handler choices for a reusable standards setup."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.creation_details import STANDARDS, StandardChoice
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_medical import Exchange
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_standards import StandardsService


def selection(values: dict[str, Any]) -> StandardChoice:
    slot = int(values["standard"][0])
    return StandardChoice(slot=slot, custom=values.get("custom", "") if slot == 9 else "")


async def open_standards(
    interaction: discord.Interaction, service: StandardsService, source_work: str | None = None
) -> None:
    data = await asyncio.to_thread(
        service.preview, viewer_from_interaction(interaction), source_work
    )
    if data["existing"]:
        await open_setup(interaction, service, data["existing"])
        return
    peers = {
        ActorRef.model_validate(x["ref"]).token: ActorRef.model_validate(x["ref"])
        for x in data["peers"]
    }
    if not peers:
        await reply(
            interaction, "A real bonded other Girl is required to choose your peer standard."
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.start,
            viewer_from_interaction(current),
            str(current.id),
            data["game_revision"],
            peers[values["peer"][0]],
            selection(values),
            source_work,
        )
        return (
            "Your standard is saved. The bonded Girl and Handler each own their choice. Request: "
            + str(result["id"])
        )

    form = NativeForm(
        interaction.user.id,
        "Your standards setup",
        "Choose your own standard and a currently bonded Girl to choose another. "
        "Your current Handler chooses the third; their standard counts as an order.",
        [
            Field(
                "peer",
                "Choose your bonded Girl",
                tuple((ActorRef.model_validate(x["ref"]).token, x["label"]) for x in data["peers"]),
            ),
            Field(
                "standard",
                "Choose your own standard",
                tuple((str(i), text) for i, text in enumerate(STANDARDS)),
            ),
            Field(
                "custom",
                "Custom standard, if chosen (up to160 characters)",
                paragraph=True,
                required=False,
            ),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_setup(
    interaction: discord.Interaction, service: StandardsService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    text = "**Original standards setup**\n" + "\n".join(
        str(x["role"]).title() + ": " + clean(x["label"]) + (" (order)" if x["is_order"] else "")
        for x in data["choices"]
    )
    if data["can_choose"]:

        async def choose(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.choose,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                selection(values),
            )
            return "Your own standard is saved. Other chooser responses remain theirs."

        form = NativeForm(
            interaction.user.id,
            "Your standard choice",
            text,
            [
                Field(
                    "standard",
                    "Choose your standard",
                    tuple((str(i), label) for i, label in enumerate(STANDARDS)),
                ),
                Field(
                    "custom",
                    "Custom standard, if chosen (up to160 characters)",
                    paragraph=True,
                    required=False,
                ),
            ],
            choose,
        )
        await reply(interaction, form.text(), form)
        return
    if data["can_finalize"]:

        async def finalize(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.finalize,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
            )
            return (
                "All three choices are recorded. Return to medical recovery "
                "to confirm your Play exchange."
                if data["source_work"]
                else "Your three actual standards are active."
            )

        form = NativeForm(
            interaction.user.id,
            "Confirm your standards",
            text,
            [
                Field(
                    "confirm",
                    "Your confirmation",
                    (("yes", "Confirm these exact three standards"),),
                )
            ],
            finalize,
        )
        await reply(interaction, form.text(), form)
        return
    if data["compiled"] and data["owner"]:

        async def finish(current: discord.Interaction, values: dict[str, Any]) -> str:
            medical = MedicalService(service.store)
            current_viewer = viewer_from_interaction(current)
            actual = await asyncio.to_thread(medical.get, current_viewer, data["source_work"])
            await asyncio.to_thread(
                medical.exchange,
                current_viewer,
                str(current.id),
                data["source_work"],
                actual["revision"],
                actual["game_revision"],
                Exchange.model_validate(actual["pending_exchange"]),
            )
            return "Your owned Play exchange and all three standards are now active."

        form = NativeForm(
            interaction.user.id,
            "Complete your pending Play exchange",
            text,
            [Field("confirm", "Your final confirmation", (("yes", "Apply my pending exchange"),))],
            finish,
        )
        await reply(interaction, form.text(), form)
        return
    if data["can_withdraw"]:

        async def withdraw(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.withdraw,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
            )
            return "Setup withdrawn. Reopen standards to nominate current actual choosers."

        form = NativeForm(
            interaction.user.id,
            "Waiting for standards",
            text,
            [
                Field(
                    "confirm", "Optional withdrawal", (("yes", "Withdraw this setup and restart"),)
                )
            ],
            withdraw,
        )
        await reply(interaction, form.text(), form)
        return
    await reply(
        interaction,
        text
        + (
            "\nOriginal context needs recovery."
            if data["stale"]
            else "\nWaiting for the original chooser's response."
        ),
    )
