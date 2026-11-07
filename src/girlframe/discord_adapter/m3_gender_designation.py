"""Private source acquisition, actual legal assignment and owned spoken-No controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_gender_designation import GenderDesignationService


async def open_designation(
    interaction: discord.Interaction, service: GenderDesignationService, identity: str | None = None
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), identity)
    if data["kind"] == "gift":
        await reply(
            interaction,
            "Actual Animal intimacy source: "
            + data["action"]
            + (
                "\nIts ordinary Tag was actually given: " + data["tag"]
                if data["tag"]
                else "\nThe Animal owns the actual Tag choice in the original Play."
            ),
        )
        return
    if data["kind"] == "speech":
        await reply(
            interaction,
            "Your actual in-character No: "
            + clean(data["account"])
            + "\nThe genuine Punishment source remains in its owned discipline card.",
        )
        return
    if data["acquisition"] is None and data["awards"]:

        async def buy(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.buy,
                viewer_from_interaction(current),
                str(current.id),
                values["award"][0],
                data["revision"],
                values["account"],
            )
            return "Gender Designation Request acquired. Open its private History card to assign."

        await NativeForm(
            interaction.user.id,
            "Acquire Gender Designation Request",
            "Spend one genuine held advancement to acquire legal-designation authority.",
            [
                Field(
                    "award",
                    "Actual held source award",
                    tuple((x["id"], clean(x["label"])[:100]) for x in data["awards"]),
                ),
                Field("account", "Actual acquisition", paragraph=True),
            ],
            buy,
        ).present(interaction)
        return
    if data["acquisition"] is not None:

        async def assign(current: discord.Interaction, values: dict[str, Any]) -> str:
            refs = tuple(
                ActorRef.model_validate(x["ref"])
                for x in data["girls"]
                if x["token"] in values["subjects"]
            )
            await asyncio.to_thread(
                service.designate,
                viewer_from_interaction(current),
                str(current.id),
                data["acquisition"],
                data["revision"],
                refs,
                values["gender"][0],
                values["account"],
            )
            return "Actual legal designation recorded. Identity and natural Status remain owned."

        await NativeForm(
            interaction.user.id,
            "Assign legal designation",
            "Select actual current Cadre Girls. You may reassign this legal status as you please.",
            [
                Field(
                    "subjects",
                    "Actual current Girls",
                    tuple((x["token"], clean(x["label"])[:100]) for x in data["girls"]),
                    maximum=min(25, len(data["girls"])),
                ),
                Field(
                    "gender",
                    "Printed legal designation",
                    (("man", "Man — he/him"), ("woman", "Woman — she/her"), ("animal", "Animal")),
                ),
                Field("account", "Actual legal assignment", paragraph=True),
            ],
            assign,
        ).present(interaction)
        return
    if data["scenes"]:

        async def choose(current: discord.Interaction, values: dict[str, Any]) -> None:
            scene = next(x for x in data["scenes"] if x["id"] == values["scene"][0])

            async def spoken(followup: discord.Interaction, fields: dict[str, Any]) -> str:
                man = next(x for x in scene["men"] if x["token"] == fields["man"][0])
                await asyncio.to_thread(
                    service.record_no,
                    viewer_from_interaction(followup),
                    str(followup.id),
                    data["revision"],
                    scene["id"],
                    ActorRef.model_validate(man["ref"]),
                    fields["account"],
                )
                return (
                    "Your actual spoken No is recorded with its genuine Handler-owned Punishment."
                )

            await NativeForm(
                current.user.id,
                "Record my actual in-character No",
                "Use only for a No you actually said to this Man. OOC decline, silence and failed "
                "compliance do not record speech or incur this source consequence.",
                [
                    Field(
                        "man",
                        "Actual addressee",
                        tuple((x["token"], clean(x["label"])[:100]) for x in scene["men"]),
                    ),
                    Field("account", "My actual spoken words and context", paragraph=True),
                ],
                spoken,
            ).present(current)

        await NativeForm(
            interaction.user.id,
            "Choose my actual speech scene",
            "Record your own performed in-character speech and its actual addressee.",
            [
                Field(
                    "scene",
                    "Actual joined scene",
                    tuple((x["id"], "Channel " + str(x["channel"])) for x in data["scenes"]),
                )
            ],
            choose,
        ).present(interaction)
        return
    await reply(
        interaction, "No held source award or applicable owned designation control is available."
    )
