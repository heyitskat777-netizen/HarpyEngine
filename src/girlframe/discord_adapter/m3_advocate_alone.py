"""Private native controls for the original Advocate and Girl."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_advocate_alone import AdvocateAloneService


async def open_question(
    interaction: discord.Interaction, service: AdvocateAloneService, revision: int, channel: int
) -> None:
    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.ask,
            viewer_from_interaction(current),
            str(current.id),
            revision,
            channel,
            values["question"],
            values["order"][0],
        )
        return "The original Girl can answer privately in her Inbox."

    await NativeForm(
        interaction.user.id,
        "Get Them Alone",
        "Ask a question in the actual one-on-one scene and select a second effect.",
        [
            Field("question", "Question", paragraph=True),
            Field(
                "order",
                "Order to issue",
                (("amuse", "Order something amusing"), ("silence", "Order her to tell nobody")),
            ),
        ],
        submit,
    ).present(interaction)


async def open_response(
    interaction: discord.Interaction, service: AdvocateAloneService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if data["issued"] or (data["handler"] != bool(data["answer"])):
        await reply(interaction, "The original choice has been saved.")
        return
    if data["handler"]:

        async def submit_order(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.issue,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values.get("message", ""),
                values["tag"],
            )
            return "The Tag is applied. The Girl can respond to the actual order."

        fields = [Field("tag", "Tag based on her answer")]
        if data["order"] == "amuse":
            fields.append(Field("message", "Actual amusing order", paragraph=True))
        await NativeForm(
            interaction.user.id,
            "Get Them Alone",
            clean(data["answer"]),
            fields,
            submit_order,
        ).present(interaction)
    else:

        async def submit_answer(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.answer,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["answer"],
            )
            return "Your original Advocate can read your answer."

        await NativeForm(
            interaction.user.id,
            "Get Them Alone",
            clean(data["question"]),
            [Field("answer", "Your own answer", paragraph=True)],
            submit_answer,
        ).present(interaction)
