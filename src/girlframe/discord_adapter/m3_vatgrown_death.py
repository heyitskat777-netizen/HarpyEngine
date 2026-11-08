"""Private fresh-creation kit and actual original respondents' noticing controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field
from girlframe.discord_adapter.m3_memory_pages import MemoryForm, MemoryHistory
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.m3_vatgrown_death import VatgrownDeathService
from girlframe.services.onboarding import WorkflowError


async def open_vatgrown_death(
    interaction: discord.Interaction, service: VatgrownDeathService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.view, viewer, identity)
    options = []
    if data["can_request"]:
        options.append(("request", "Request your saved reviewed new physical kit"))
    if data["can_issue"]:
        options.append(("issue", "Record actual distinct kit issued at a Foundation base"))
    if data["owner"] and data["issue"] and not data["source"]["activated_event"]:
        options.append(("activate", "Activate the actual distinct reviewed Vatgrown"))
    options += [("notice:" + x, "Answer your own noticing question") for x in data["pending"]]
    lines = [
        "Distinct Vatgrown replacement: " + data["phase"],
        "The original person and equipment remain archived. Fresh creation and new starting "
        "Bonds are required; this is another Girl. Complete and save the ordinary new creation "
        "review, then request its physical kit.",
    ]
    if data["kit"]:
        lines.append(
            "Requested new Frame: " + data["kit"]["frame_name"] + " / " + data["kit"]["frame"]
        )
        lines.extend(
            "New " + family + ": " + x["name"] + " — " + x["description"]
            for family, key in (
                ("body component", "girl_assets"),
                ("Frame component", "frame_assets"),
            )
            for x in data["kit"][key]
        )
    if data["issue"]:
        lines.append(
            "Actual supplied kit at map "
            + str(tuple(data["issue"]["cell"]))
            + ": "
            + data["issue"]["account"]
        )
    for notice in data["notices"]:
        lines.append(
            notice["label"]
            + " — Do you notice this is not the original Girl anymore? "
            + (
                (notice["answer"] + ": " + notice["account"])
                if notice["response_event"]
                else "Awaiting that original person's own answer."
            )
        )

    async def access(current: discord.Interaction) -> None:
        await asyncio.to_thread(service.view, viewer_from_interaction(current), identity)

    if not options:
        history = MemoryHistory(interaction.user.id, "\n".join(lines), access)
        await reply(interaction, history.text(), history)
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        operation = values.get("operation", ("",))[0]
        if operation not in dict(options):
            raise WorkflowError("Choose one of your actual available source operations")
        person = viewer_from_interaction(current)
        if operation == "request":
            await asyncio.to_thread(
                service.request_issue, person, str(current.id), identity, data["revision"]
            )
            return "Reviewed kit requested. The actual Handler must record its physical supply."
        if operation == "issue":
            if not all(str(values.get(key, "")).strip() for key in ("x", "y", "account")):
                raise WorkflowError(
                    "Record actual base coordinates and the physical supply account"
                )
            try:
                cell = (int(values["x"]), int(values["y"]))
            except (ValueError, TypeError):
                raise WorkflowError("Enter actual integer map coordinates") from None
            await asyncio.to_thread(
                service.issue,
                person,
                str(current.id),
                identity,
                data["revision"],
                data["request"],
                cell,
                values["account"],
            )
            return "Actual distinct reviewed kit supply recorded. The new Girl activates herself."
        if operation == "activate":
            review = await asyncio.to_thread(CreationReviewService(service.store).get, person)
            await asyncio.to_thread(
                service.game.activate, person, str(current.id), review.fingerprint
            )
            return "Distinct Vatgrown activated. Other original people own their noticing replies."
        notice = operation.removeprefix("notice:")
        selected = values.get("answer", ())
        if not selected or not str(values.get("account", "")).strip():
            raise WorkflowError("Choose your own noticing result and write your actual account")
        await asyncio.to_thread(
            service.answer,
            person,
            str(current.id),
            identity,
            data["revision"],
            notice,
            values["answer"][0],
            values["account"],
        )
        return "Your actual own noticing answer is saved privately."

    fields = [Field("operation", "Your actual source operation", tuple(options))]
    if data["can_issue"]:
        fields.extend(
            [
                Field("x", "Actual Foundation-base map x", required=False),
                Field("y", "Actual Foundation-base map y", required=False),
            ]
        )
    if data["pending"]:
        fields.append(
            Field(
                "answer",
                "Your own noticing",
                (("yes", "Yes"), ("no", "No"), ("uncertain", "Uncertain")),
                minimum=0,
                required=False,
            )
        )
    if data["can_issue"] or data["pending"]:
        fields.append(
            Field(
                "account",
                "Your actual supply or own noticing account",
                paragraph=True,
                required=False,
            )
        )
    form = MemoryForm(
        interaction.user.id,
        "Distinct Vatgrown / owned noticing",
        "\n".join(lines),
        fields,
        submit,
        authorize=access,
    )
    await reply(interaction, form.text(), form)
