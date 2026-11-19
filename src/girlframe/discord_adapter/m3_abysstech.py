"""Native original contact and private Experimental Abysstech choices."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_abysstech import AbysstechService


async def open_abysstech(
    interaction: discord.Interaction, service: AbysstechService, channel: int, actor: ActorRef
) -> None:
    data = await asyncio.to_thread(
        service.menu,
        viewer_from_interaction(interaction),
        channel,
        actor,
    )
    if not data["people"] or not data["tools"]:
        await reply(interaction, "Recover your actual working tool and an available local Girl.")
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.propose,
            viewer_from_interaction(click),
            str(click.id),
            channel,
            actor,
            data["revision"],
            values["tool"][0],
            values["person"][0],
            values["account"],
        )
        return "The original owner can confirm the actual contact in her private Inbox."

    form = NativeForm(
        interaction.user.id,
        "Experimental Abysstech",
        "Record your use of an actual tool in the original scene.",
        [
            Field("person", "Original local Girl", tuple(data["people"].items())),
            Field("tool", "Your actual tool", tuple(data["tools"].items())),
            Field("account", "What did your Acolyte do?", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_abysstech_contact(
    interaction: discord.Interaction, service: AbysstechService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    step = data["step"]
    if step == "contact":
        choices = (("decline", "Decline or no contact"), *data["assets"].items())
        text = "Choose only the actual contacted Asset you approve revealing.\n" + clean(
            data["account"]
        )
    elif step == "choose":
        choices = (("heat", "Gain two Heat"), ("pressure", "Ask her to choose a consequence"))
        text = "Contact confirmed with " + clean(data["asset"]) + ". Choose a printed effect."
    else:
        choices = (
            ("damage", "Damage the original contacted Asset"),
            ("helpless", "Become Helpless against this Acolyte"),
        )
        text = "Choose your actual consequence from the original contact."

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            step,
            values["choice"][0],
        )
        return "Your original Abysstech decision is saved."

    form = NativeForm(
        interaction.user.id,
        "Experimental Abysstech",
        text,
        [Field("choice", "Your original choice", choices)],
        submit,
    )
    await reply(interaction, form.text(), form)
