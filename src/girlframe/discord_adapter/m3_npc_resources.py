"""Private witnessed NPC resource setup/readback through ordinary native forms."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_memory_pages import MemoryHistory
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_npc_resources import NpcResourcesService
from girlframe.services.onboarding import WorkflowError


async def open_npc_resources(
    interaction: discord.Interaction,
    service: NpcResourcesService,
    target: ActorRef | None = None,
) -> None:
    viewer = viewer_from_interaction(interaction)
    channel = int(interaction.channel_id or 0)
    data = await asyncio.to_thread(service.menu, viewer, channel)
    if target is None:
        rows = [row for row in data["actors"] if row["may_record"] or row["may_view"]]
        if not rows:
            await reply(interaction, "No witnessed NPC resource setup is available in this scene.")
            return

        async def choose(current: discord.Interaction, token: str) -> None:
            row = next(row for row in rows if row["token"] == token)
            await open_npc_resources(current, service, ActorRef.model_validate(row["ref"]))

        await Picker(
            viewer.user_id,
            "**Actual NPC treatment resources**",
            tuple((row["token"], row["label"]) for row in rows),
            choose,
        ).show(interaction)
        return
    row = next((row for row in data["actors"] if row["token"] == target.token), None)
    if row is None:
        raise WorkflowError("Use the actual original NPC in this source scene")
    if row["recorded"]:
        shown = await asyncio.to_thread(service.view, viewer, target)
        value = shown["resources"]
        text = "\n".join(
            [
                "**Witnessed NPC resources — " + clean(shown["label"]) + "**",
                "Heat: " + str(value["heat"]),
                *[
                    clean(x["name"]) + (" — marked" if x["marked"] else " — unmarked")
                    for x in value["identities"]
                ],
                "Actual source account: " + clean(value["account"]),
                "Original source: " + clean(value["source_event"]),
            ]
        )

        async def read(current: discord.Interaction) -> None:
            await asyncio.to_thread(service.view, viewer_from_interaction(current), target)

        history = MemoryHistory(viewer.user_id, text, read)
        await reply(interaction, history.text(), history)
        return
    if not row["may_record"]:
        raise WorkflowError("The appointed Handler records positive existing NPC resource facts")

    async def count_selected(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        count = int(values["count"][0])
        fields = [
            Field("heat", "Actual existing Heat"),
            Field("account", "Witnessed resource facts", paragraph=True),
        ]
        for number in range(count):
            fields.extend(
                [
                    Field("name_" + str(number), "Identity " + str(number + 1) + " name"),
                    Field(
                        "marked_" + str(number),
                        "Identity " + str(number + 1) + " state",
                        (("yes", "Marked"), ("no", "Unmarked")),
                    ),
                ]
            )

        async def submit(response: discord.Interaction, answers: dict[str, Any]) -> str:
            try:
                heat = int(answers["heat"])
            except (TypeError, ValueError):
                raise WorkflowError("Enter the NPC's actual non-negative whole Heat") from None
            saved = await asyncio.to_thread(
                service.record,
                viewer_from_interaction(response),
                str(response.id),
                data["revision"],
                channel,
                target,
                heat,
                tuple(
                    (answers["name_" + str(i)], answers["marked_" + str(i)][0] == "yes")
                    for i in range(count)
                ),
                answers["account"],
            )
            return "The actual original NPC resource source is saved privately: " + str(saved["id"])

        await NativeForm(
            viewer.user_id,
            "Witness actual NPC resources",
            "Record established facts, not a new Girl sheet or treatment reward. "
            "No default Heat or Identities are granted. Assets keep their real custody.",
            fields,
            submit,
        ).present(current)
        return None

    await NativeForm(
        viewer.user_id,
        "Witness NPC Identities",
        "How many ordinary Identities have actually been established for this NPC?",
        [Field("count", "Existing ordinary Identities", tuple((str(i), str(i)) for i in range(5)))],
        count_selected,
    ).present(interaction)
