"""Native NPC item offers with a private choice for the original Girl."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_npc_handover import LABELS, Job, NpcHandoverService


async def open_handover(
    interaction: discord.Interaction,
    service: NpcHandoverService,
    channel: int,
    actor: ActorRef,
    job: Job,
) -> None:
    data = await asyncio.to_thread(
        service.menu, viewer_from_interaction(interaction), channel, actor, job
    )
    if not data["targets"] or (job != "fan" and not data["items"]):
        await reply(interaction, "There is no eligible local recipient and possession to offer.")
        return
    prompts = {
        "fan": "What is your Fan trying to take?",
        "patron": "Why does your Patron offer this object?",
        "smuggler": "Why is this item forbidden to her?",
    }
    fields = [
        Field("target", "Original Girl", tuple(data["targets"].items())),
        Field("account", prompts[job], paragraph=True),
    ]
    if job != "fan":
        fields.append(Field("item", "Actual held object", tuple(data["items"].items())))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.propose,
            viewer_from_interaction(current),
            str(current.id),
            channel,
            actor,
            job,
            data["revision"],
            values["target"][0],
            values["account"],
            values["item"][0] if "item" in values else None,
        )
        return "The original Girl has the private choice."

    form = NativeForm(
        interaction.user.id, LABELS[job], "Use your actual NPC’s current scene.", fields, submit
    )
    await reply(interaction, form.text(), form)


async def open_handover_choice(
    interaction: discord.Interaction, service: NpcHandoverService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    options = (
        *((f"item/{key}", value) for key, value in data["items"].items()),
        ("decline", "Decline"),
    )
    question = "Choose what the Fan takes" if data["job"] == "fan" else "Accept the offered item"

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        selected = values["choice"][0]
        result = await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            selected.removeprefix("item/") if selected.startswith("item/") else None,
        )
        return "The actual possession changed hands." if result["transfer"] else "You declined."

    form = NativeForm(
        interaction.user.id,
        LABELS[data["job"]],
        clean(data["account"]),
        [Field("choice", question, options)],
        submit,
    )
    await reply(interaction, form.text(), form)
