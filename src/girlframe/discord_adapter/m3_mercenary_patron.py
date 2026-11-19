"""Native control of the exact NPC sponsorship funding the original Mercenary."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_mercenary_patron import MercenaryPatronService

TITLE = "Mercenary patronage"


async def open_patron(
    interaction: discord.Interaction,
    service: MercenaryPatronService,
    channel: int,
    actor: ActorRef,
) -> None:
    viewer = viewer_from_interaction(interaction)
    withdrawing = actor.kind == "npc"
    if withdrawing:
        data = await asyncio.to_thread(service.withdrawal_menu, viewer, channel, actor)
        options = tuple(data["people"].items())
        text = "Withdraw your own active NPC sponsorship in the original scene."
    else:
        data = await asyncio.to_thread(service.menu, viewer, channel, actor)
        options = tuple(data["prospects"].items())
        text = "Choose an actual new Patron in the original scene."
    if not options:
        status = (
            "Your sponsorship is currently active with " + clean(data["patron"]) + "."
            if data.get("funded")
            else "No eligible decision is available in this scene."
        )
        await reply(interaction, status)
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        act = service.withdraw if withdrawing else service.request
        await asyncio.to_thread(
            act,
            viewer_from_interaction(click),
            str(click.id),
            channel,
            actor,
            data["revision"],
            values["person"][0],
            values["account"],
        )
        return (
            "The original funding has ended and its recipient can see the notice."
            if withdrawing
            else "The original Patron has a private proposal."
        )

    form = NativeForm(
        interaction.user.id,
        TITLE,
        text,
        [
            Field("person", "The original person", options),
            Field("account", "Record the actual sponsorship change", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_patron_inbox(
    interaction: discord.Interaction,
    service: MercenaryPatronService,
    identity: str,
    step: str,
) -> None:
    viewer = viewer_from_interaction(interaction)
    if step == "loss":
        data = await asyncio.to_thread(service.loss, viewer, identity)
        await reply(
            interaction,
            "Your funding from "
            + clean(data["patron"])
            + " ended. You may seek a new Patron in the original scene.",
        )
        return
    if step == "death":
        data = await asyncio.to_thread(service.death, viewer, identity)
        instructions = "Verify the actual death of " + clean(data["patron"]) + "."
        fields = [Field("account", "Record the actual original loss", paragraph=True)]
    else:
        data = await asyncio.to_thread(service.offer, viewer, identity)
        instructions = clean(data["mercenary"]) + " requests your actual patronage.\n"
        instructions += clean(data["invitation"])
        fields = [Field("choice", "Your decision", (("yes", "Accept"), ("no", "Decline")))]

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        args = viewer_from_interaction(click), str(click.id), identity, data["revision"]
        if step == "death":
            await asyncio.to_thread(service.verify_death, *args, values["account"])
            return "The original funding loss is recorded."
        accepted = values["choice"][0] == "yes"
        await asyncio.to_thread(service.respond, *args, accepted)
        return "The original Patron decision is saved."

    form = NativeForm(interaction.user.id, TITLE, instructions, fields, submit)
    await reply(interaction, form.text(), form)
