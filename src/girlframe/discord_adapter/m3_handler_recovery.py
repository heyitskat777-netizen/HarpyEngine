"""Private reopenable actual Handler rescue release and patient fact confirmation."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field
from girlframe.discord_adapter.m3_memory_pages import MemoryForm, MemoryHistory
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_handler_recovery import HandlerRecoveryService
from girlframe.services.onboarding import WorkflowError


async def open_handler_recovery(
    interaction: discord.Interaction,
    service: HandlerRecoveryService,
    identity: str,
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    text = "\n".join(
        [
            "**Actual Handler rescue discharge**",
            "Original Defeat: " + data["source_action"],
            "Original body: " + data["vessel"],
            "State: " + data["phase"].replace("_", " "),
            "Current actual Handler cell: " + str(data["cell"]),
            "This records witnessed release facts. It grants no repair or unperformed transport.",
        ]
    )
    if data["blocked"]:
        text += "\nStill required: " + data["blocked"]
    if data["proposal"]:
        text += "\nHandler's witnessed account: " + data["proposal"]["account"]
        text += "\nProposed actual release cell: " + str(data["proposal"]["cell"])
    if data["release"]:
        text += "\nPatient's confirmed facts: " + data["release"]["account"]

    async def authorize(current: discord.Interaction) -> None:
        await asyncio.to_thread(service.get, viewer_from_interaction(current), identity)

    actions = []
    if data["may_record_presence"]:
        actions.append(("presence", "Witness previously unknown initial Handler position"))
    if data["may_propose"]:
        actions.append(("propose", "Propose actual release at the current Handler position"))
    if data["may_confirm"]:
        actions.append(("confirm", "Confirm this original body and actual release facts"))
    if not actions:
        history = MemoryHistory(viewer.user_id, text, authorize)
        await reply(interaction, history.text(), history)
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        selected = values["action"][0]
        fields = [Field("account", "Actual witnessed facts", paragraph=True)]
        if selected == "presence":
            board = data["board"]
            if board is None:
                raise WorkflowError("Establish the actual map before recording initial presence")
            fields.insert(
                0,
                Field(
                    "cell",
                    "Actual current initial position",
                    tuple(
                        (str(x) + "," + str(y), "(" + str(x) + ", " + str(y) + ")")
                        for x in range(board["minimum"][0], board["maximum"][0] + 1)
                        for y in range(board["minimum"][1], board["maximum"][1] + 1)
                    ),
                ),
            )

        async def submit(response: discord.Interaction, answers: dict[str, Any]) -> str:
            owner = viewer_from_interaction(response)
            if selected == "presence":
                x, y = answers["cell"][0].split(",")
                await asyncio.to_thread(
                    service.record_initial_presence,
                    owner,
                    str(response.id),
                    identity,
                    data["revision"],
                    (int(x), int(y)),
                    answers["account"],
                )
                return "The actual initial Handler presence is saved. Reopen this release."
            if selected == "propose":
                await asyncio.to_thread(
                    service.propose,
                    owner,
                    str(response.id),
                    identity,
                    data["revision"],
                    answers["account"],
                )
                return (
                    "The witnessed release is saved. "
                    "The original patient confirms the actual facts."
                )
            if selected != "confirm" or data["proposal"] is None:
                raise WorkflowError("Reopen the original release proposal")
            await asyncio.to_thread(
                service.confirm,
                owner,
                str(response.id),
                identity,
                data["revision"],
                data["proposal"]["event"],
                answers["account"],
            )
            return (
                "The original patient's release facts are saved; actual source custody is cleared."
            )

        await MemoryForm(
            viewer.user_id,
            "Confirm witnessed rescue facts",
            text,
            fields,
            submit,
            authorize=authorize,
        ).present(current)
        return None

    await MemoryForm(
        viewer.user_id,
        "Actual Handler rescue",
        text,
        [Field("action", "Current original source task", tuple(actions))],
        choose,
        authorize=authorize,
    ).present(interaction)
