"""Native controls for original NPC job requests and Girl responses."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_journalist import Job
from girlframe.services.m3_journalist import JournalistService


async def open_ask(
    interaction: discord.Interaction,
    service: JournalistService,
    channel: int,
    reporter: ActorRef,
    *,
    job: Job = "journalist",
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.targets, viewer, channel, reporter, job=job)
    title, prompt, effect = {
        "journalist": (
            "Ask a direct Journalist question",
            "What do you ask?",
            Field("tag", "Tag on refusal"),
        ),
        "family": (
            "Point out an actual change",
            "What change do you point out?",
            Field("tag", "Tag if the change stays uncorrected"),
        ),
        "psychologist": (
            "Give a directive and an Identity",
            "What do you direct her to do?",
            Field("identity", "New Identity"),
        ),
        "public_relations": (
            "Set a Public Relations expectation",
            "What do you expect her to do?",
            Field("tag", "Tag if the expectation falls through"),
        ),
    }[job]
    if not data["targets"]:
        await reply(interaction, "Choose a scene with your original NPC and an addressed Girl.")
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
            values.get("tag", ""),
            job=job,
            identity_label=values.get("identity"),
        )
        return "The original Girl can respond from her private Inbox."

    form = NativeForm(
        viewer.user_id,
        title,
        "The addressed Girl owns her response.",
        [
            Field("girl", "Which Girl do you address?", data["targets"]),
            Field("question", prompt, paragraph=True),
            effect,
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
    family = data["job"] == "family"
    psychology = data["job"] == "psychologist"
    public_relations = data["job"] == "public_relations"
    if psychology:
        question += "\nNew Identity · " + clean(data["identity_label"])
        if data["can_answer"] and data["needs_replacement"] and not data["replacements"]:
            await reply(
                interaction,
                question + "\nThis request needs human review of the existing Identity slots.",
            )
            return
    if not data["can_answer"]:
        if data["reply"]:
            status = "\n" + clean(data["reply"])
        elif psychology and data["response"] == "answer":
            status = "\nThe original Girl received the Identity."
        elif data["response"] == "decline":
            status = "\nThe change remains uncorrected." if family else "\nDeclined in character."
        else:
            status = "\nAwaiting the original Girl's response."
        await reply(interaction, (question + status)[:1950])
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            values.get("response", ("answer",))[0],
            values.get("reply", ""),
            replace=values.get("replace", (None,))[0],
            unmark=next(iter(values.get("unmark", ())), None),
        )
        return "Your response was saved."

    if psychology:
        fields = (
            [Field("replace", "Your own Identity to replace", data["replacements"])]
            if data["needs_replacement"]
            else []
        )
        form = NativeForm(
            viewer.user_id,
            "Receive the Psychologist's Identity",
            question,
            fields
            + [
                Field("response", "Confirm the Identity", (("answer", "Add this Identity"),)),
            ],
            submit,
        )
        await reply(interaction, form.text(), form)
        return

    if public_relations:
        outcomes: tuple[tuple[str, str], ...] = (("decline", "Could not meet the expectation"),)
        if data["marked_identities"]:
            outcomes += (("answer", "Met the expectation"),)
            instruction = "Meeting it unmarks an Identity. Falling short gives your Girl a Tag."
            fields = [
                Field(
                    "unmark",
                    "Identity to unmark if you met the expectation",
                    data["marked_identities"],
                    minimum=0,
                    required=False,
                )
            ]
        else:
            instruction = (
                "You can report falling short. If you met the expectation, leave this pending "
                "for human review of the Identity reward."
            )
            fields = []
        form = NativeForm(
            viewer.user_id,
            "Respond to the Public Relations expectation",
            question + "\n" + instruction,
            [
                Field("response", "What happened?", outcomes),
                Field("reply", "Describe what actually happened", paragraph=True),
            ]
            + fields,
            submit,
        )
        await reply(interaction, form.text(), form)
        return

    form = NativeForm(
        viewer.user_id,
        "Respond to the Family NPC" if family else "Respond to the Journalist",
        question
        + (
            "\nLeaving the discrepancy uncorrected gives your Girl a Tag."
            if family
            else "\nAn in-character refusal gives your Girl a Tag."
        ),
        [
            Field(
                "response",
                "Your own response",
                (("answer", "Describe the actual correction"), ("decline", "Leave it uncorrected"))
                if family
                else (("answer", "Answer"), ("decline", "Decline in character")),
            ),
            Field("reply", "Your reply", paragraph=True, required=False),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
