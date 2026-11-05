"""Private complete dossier files and one owned question/Handler answer."""

import asyncio
import io
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.services.m2_game import GameService
from girlframe.services.m3_am_records import RecordsService


async def open_document(
    interaction: discord.Interaction, service: RecordsService, identity: str
) -> None:
    value = await asyncio.to_thread(
        service.document, viewer_from_interaction(interaction), identity
    )
    text = (
        f"Foundation records: {value['subject']}\nSource: {value['reference']}\n\n"
        f"Complete unredacted stored record:\n{value['document']}\n\n"
        f"One question: {value['question']}\nActual answer: {value['answer']}\n"
    )
    attachment = discord.File(
        io.BytesIO(text.encode()), filename="foundation-record-" + identity + ".txt"
    )
    options: dict[str, Any] = dict(
        content="Your actual learned Foundation record; private to its original learner.",
        file=attachment,
        ephemeral=True,
        allowed_mentions=discord.AllowedMentions.none(),
    )
    if interaction.response.is_done():
        await interaction.followup.send(**options)
    else:
        await interaction.response.send_message(**options)


async def open_choice(interaction: discord.Interaction, game: GameService, identity: str) -> None:
    data = await asyncio.to_thread(game.decision, viewer_from_interaction(interaction), identity)
    detail = data["am_code"]["records"]
    fields = [Field("account", "One actual question about this person's records", paragraph=True)]
    if data["kind"] == "am_code_records_answer":
        fields = [
            Field("account", "Actual honest Foundation-record answer", paragraph=True),
            Field("honest", "This is the actual honest record-grounded answer", (("yes", "Yes"),)),
        ]
    else:
        # The full acquired document is delivered privately, never shortened into a public summary.
        pointer = data["am_code"]["records_id"]
        await open_document(interaction, RecordsService(game), pointer)

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            ChoiceAnswer(
                text=values["account"],
                flag=True
                if data["kind"] == "am_code_records_answer" and values["honest"] == ("yes",)
                else None,
            ),
        )
        return (
            "Your actual private records response is saved; "
            "other selected effects still require completion."
        )

    form = NativeForm(
        interaction.user.id,
        "Foundation records: " + detail["subject"],
        (
            "Only the actual operator asks this one question. "
            if data["kind"] == "am_code_records_question"
            else "Actual question: "
            + detail["question"]
            + "\nAnswer from the complete prepared record. "
        )
        + "No transcript is automatically given to the AM or other people.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)
