"""Native owned-role preview; stable entity tokens distinguish identical names."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.labels import entity_label
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_actors import ActorService

LABELS = {
    "pilot": "Girl",
    "npc": "NPC",
    "external_pilot": "External Pilot",
    "gorgon": "Gorgon",
    "handler": "Handler",
}


async def open_actors(interaction: discord.Interaction, service: ActorService) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.choices, viewer)
    options = tuple(
        (x["token"], x["label"][:78] + " (" + LABELS[x["kind"]] + ")") for x in data["actors"]
    )
    if data["legacy_binding_available"]:
        options += (("bind-legacy", "Link your original character to its saved sheet"),)
    if not options:
        await reply(
            interaction,
            "No current role is available. Check requests for activation or NPC invitations.",
        )
        return
    actors = {x["token"]: x for x in data["actors"]}

    async def choose(current: discord.Interaction, token: str) -> None:
        if token == "bind-legacy":

            async def submit(actor: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.bind_legacy,
                    viewer_from_interaction(actor),
                    str(actor.id),
                    data["game_revision"],
                )
                return "The original character link is saved. Reopen /mission actors."

            form = NativeForm(
                viewer.user_id,
                "Link original character",
                "Confirm the link between your original character and its saved sheet. "
                "The original snapshot must agree with the current profile.",
                [Field("confirm", "Confirm", (("yes", "Link my original character"),))],
                submit,
            )
            await reply(current, form.text(), form)
            return
        ref = ActorRef.model_validate(actors[token]["ref"])
        result = await asyncio.to_thread(service.inspect, viewer_from_interaction(current), ref)
        own = result["actor"]
        text = "**" + own["label"] + " — " + LABELS[ref.kind] + "**\n"
        text += "Rules: " + own["rules"].replace("_", " ") + "\n"
        if own["heat"] is not None:
            text += "Heat: " + str(own["heat"]) + "\n"
        text += "\n".join(
            entity_label(x) + (" — marked" if x["marked"] else " — unmarked")
            for x in own["identities"]
        )
        text += "\nAssets: " + str(len(own["assets"]))
        text += "\nThis is your saved role preview. Available Plays use their own controls."
        await reply(current, text[:1800])

    view = Picker(
        viewer.user_id,
        "**Your current roles**\nChoose the actual character you want to review.",
        options,
        choose,
    )
    await view.show(interaction)
