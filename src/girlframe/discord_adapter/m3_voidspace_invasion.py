"""Private native Voidspace Invasion roll and onward route."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_harpy_defeat import HarpyDefeatService
from girlframe.services.m3_voidspace_invasion import InvasionService


async def open_invasion(
    interaction: discord.Interaction, service: InvasionService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    step = data["step"]
    if step == "roll":
        text = "The original Cadre crossed together. Roll with the original Ace’s Void Assets."
        fields = [
            Field("ace", "Actual Ace", tuple(data["aces"].items())),
            Field("account", "Describe the original crossing", paragraph=True),
        ]
    elif step == "review" and data["tier"] in ("mid", "high"):
        text = f"Original dice {data['faces']} plus {data['modifier']} Void Assets."
        fields = [Field("account", "Describe the actual route found", paragraph=True)]
    elif step == "route":
        text = clean(data["route"])
        if data["encounter"]:
            text += "\nEncounter " + clean(data["encounter"])
        if data["traveler"] is None:
            await reply(interaction, text)
            return
        fields = [Field("account", "Describe your actual onward journey", paragraph=True)]
    elif step == "encounter":
        if not data["encounters"]:
            await reply(interaction, "The original outcome still awaits a verified encounter.")
            return
        text = "Choose which actual being the Cadre encountered."
        fields = [
            Field("target", "Actual encounter", tuple(data["encounters"].items())),
            Field("account", "Describe the verified encounter", paragraph=True),
        ]
    elif step == "gain":
        if not data["assets"]:
            await reply(interaction, "Your original gain needs an eligible Asset or human review.")
            return
        text = clean(data["encounter"])
        fields = [
            Field("asset", "Your actual eligible Asset", tuple(data["assets"].items())),
            Field("account", "Describe the actual Void alteration", paragraph=True),
        ]
    elif step in ("report", "settled"):
        summary = (
            "The original Cadre’s Void outcome is resolved."
            if step == "settled"
            else "Your original Void response is saved. Cadre work is still pending."
        )
        await reply(interaction, summary + "\n" + clean(data["encounter"]))
        return
    else:
        await reply(interaction, "The exact original roll is saved and its discovery is pending.")
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        viewer = viewer_from_interaction(click)
        if step == "roll":
            await asyncio.to_thread(
                service.start,
                viewer,
                str(click.id),
                identity,
                data["revision"],
                values["ace"][0],
                values["account"],
            )
            return "The original Cadre’s roll is saved."
        if step == "review":
            await asyncio.to_thread(
                service.route, viewer, str(click.id), identity, data["revision"], values["account"]
            )
            return "The original Cadre can use the discovered route."
        if step == "encounter":
            await asyncio.to_thread(
                service.encounter,
                viewer,
                str(click.id),
                identity,
                data["revision"],
                values["target"][0],
                values["account"],
            )
            return "The verified original encounter is saved."
        if step == "gain":
            await asyncio.to_thread(
                service.gain,
                viewer,
                str(click.id),
                identity,
                data["revision"],
                values["asset"][0],
                values["account"],
            )
            return "Your original Void gain is saved. Check your Inbox for any threshold."
        await asyncio.to_thread(
            HarpyDefeatService(service.store, service.game).propose_route,
            viewer,
            str(click.id),
            data["revision"],
            ActorRef.model_validate(data["traveler"]),
            discovery=data["discovery"],
            navigation="",
            account=values["account"],
        )
        return "The original facilitator can verify your onward route."

    form = NativeForm(interaction.user.id, "Voidspace Invasion", text, fields, submit)
    await reply(interaction, form.text(), form)
