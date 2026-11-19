"""Owned Journalist questions and the original Girl's private answer."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_journalist import JournalistService


async def open_ask(
    interaction: discord.Interaction, service: JournalistService, channel: int, reporter: ActorRef
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.targets, viewer, channel, reporter)
    if not data["targets"]:
        await reply(
            interaction, "Choose a scene with your original Journalist and an addressed Girl."
        )
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.ask,
            viewer_from_interaction(click),
            str(click.id),
            channel,
            data["revision"],
            reporter,
            int(values["girl"][0]),
            values["question"],
            values["tag"],
        )
        return "The original Girl can respond from her private Inbox."

    form = NativeForm(
        viewer.user_id,
        "Ask a direct Journalist question",
        "The addressed Girl owns her answer.",
        [
            Field("girl", "Which Girl do you address?", data["targets"]),
            Field("question", "What do you ask?", paragraph=True),
            Field("tag", "Tag if she declines in character"),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_response(
    interaction: discord.Interaction, service: JournalistService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.view, viewer, identity)
    question = clean(data["question"])
    if not data["can_answer"]:
        status = (
            ("\n" + clean(data["reply"]))
            if data["reply"]
            else (
                "\nDeclined in character."
                if data["response"] == "decline"
                else "\nAwaiting the original Girl's response."
            )
        )
        await reply(interaction, (question + status)[:1950])
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            values["response"][0],
            values.get("reply", ""),
        )
        return "Your response was saved."

    form = NativeForm(
        viewer.user_id,
        "Respond to the Journalist",
        question + "\nAn in-character refusal gives your Girl a Tag.",
        [
            Field(
                "response",
                "Your own response",
                (("answer", "Answer"), ("decline", "Decline in character")),
            ),
            Field("reply", "Your reply", paragraph=True, required=False),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
