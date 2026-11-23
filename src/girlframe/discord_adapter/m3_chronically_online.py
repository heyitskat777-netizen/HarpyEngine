"""Private native controls for the Revolutionary's prior facts and meeting."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_chronically_online import LABELS, ChronicallyOnlineService, PriorFact

TITLE = "Chronically Online"


async def open_recollection(
    interaction: discord.Interaction,
    service: ChronicallyOnlineService,
    channel: int,
    actor: ActorRef,
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.menu, viewer, channel, actor)
    if not data["people"]:
        await reply(interaction, "There is no eligible Pilot to recall facts about before meeting.")
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        facts = (
            PriorFact(category=values["first"][0], text=values["first_text"]),
            PriorFact(category=values["second"][0], text=values["second_text"]),
        )
        await asyncio.to_thread(
            service.propose,
            viewer_from_interaction(click),
            str(click.id),
            channel,
            actor,
            data["revision"],
            values["pilot"][0],
            facts,
            values["source"],
        )
        return "The original Pilot has a private request to verify your earlier knowledge."

    form = NativeForm(
        interaction.user.id,
        TITLE,
        "Recall two facts you already knew about this Pilot.",
        [
            Field("pilot", "Actual original Pilot", tuple(data["people"].items())),
            Field("first", "First known category", tuple(LABELS.items())),
            Field("first_text", "First known fact"),
            Field("second", "Second known category", tuple(LABELS.items())),
            Field("second_text", "Second known fact"),
            Field("source", "How you already knew both facts", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_recollection_inbox(
    interaction: discord.Interaction,
    service: ChronicallyOnlineService,
    identity: str,
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    options: tuple[tuple[str, str], ...]
    if data["step"] == "confirm":
        instructions = "Confirm these statements were true and already known to the Revolutionary."
        options = (("yes", "Confirm earlier knowledge"), ("no", "Decline confirmation"))
    elif data["step"] == "meet":
        instructions = "Record that you met the Pilot here and ask them to confirm."
        options = (("met", "Record that we met"),)
    else:
        instructions = "Confirm that you met the Revolutionary here for the two verified Tags."
        options = (("apply", "Confirm the meeting and apply both Tags"), ("no", "We have not met"))
    for fact in data["facts"]:
        instructions += "\n" + clean(LABELS[fact.category]) + " — " + clean(fact.text)
    instructions += "\nPrior source — " + clean(data["source"])

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.act,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            values["choice"][0],
        )
        return "The original decision is saved."

    form = NativeForm(
        interaction.user.id,
        TITLE,
        instructions,
        [Field("choice", "Your decision", options)],
        submit,
    )
    await reply(interaction, form.text(), form)
