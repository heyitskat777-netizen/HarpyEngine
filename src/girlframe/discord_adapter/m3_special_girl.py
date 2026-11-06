"""Actual Handler naming and original owner slot selection for the paid token."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_special_girl import SpecialGirlService
from girlframe.services.onboarding import WorkflowError


async def open_special_girl(interaction: discord.Interaction, service: SpecialGirlService) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction))
    if not data["available"]:
        raise WorkflowError("No reviewed Handler's Special Girl acquisition is available")
    if data["owned"]:
        await open_token(interaction, service, data["request"])
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.buy,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            ActorRef.model_validate(data["actor"]),
            data["frame"],
            values["account"],
            values["donor"][0] if data["donors"] else None,
        )
        return (
            "Acquisition saved. Your actual Handler must name and describe "
            "the token in their inbox."
        )

    await NativeForm(
        interaction.user.id,
        f"Handler's Special Girl — {data['kind'].replace('_', ' ').title()}, "
        f"{data['price']} Permissions",
        "Your actual Handler supplies a token of affection as a Girl Asset. "
        "You choose any required ordinary non-Void Girl Asset replacement.",
        (
            [Field("donor", "Actual Autocrat donor Frame", tuple((x, x) for x in data["donors"]))]
            if data["donors"]
            else []
        )
        + [Field("account", "Record your actual acquisition", paragraph=True)],
        submit,
    ).present(interaction)


async def open_token(
    interaction: discord.Interaction, service: SpecialGirlService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    token = data["token"]
    if token["phase"] == "complete":
        await reply(
            interaction,
            "Original Handler-authored token received: "
            + token["asset"]["name"]
            + "\n"
            + token["asset"]["description"],
        )
        return
    if not data["can_act"]:
        await reply(
            interaction,
            "This original token is waiting for its actual Handler or owner. "
            "Restore the original paid source and roles before its next response.",
        )
        return
    if token["phase"] == "handler":
        fields = [
            Field("name", "Name the token you actually give her"),
            Field("description", "Describe your actual token of affection", paragraph=True),
        ]
        instructions = (
            "As the original Handler, name and describe the actual Girl Asset you give her."
        )
    else:
        if data["needs_replace"] and not data["replacements"]:
            raise WorkflowError(
                "The real token waits until a legal non-Void Girl Asset slot is available"
            )
        fields = (
            [
                Field(
                    "replace",
                    "Choose the ordinary non-Void Girl Asset to replace",
                    tuple((x["id"], x["label"]) for x in data["replacements"]),
                )
            ]
            if data["needs_replace"]
            else []
        )
        if not fields:
            fields = [
                Field(
                    "receive",
                    "Receive the exact authored token",
                    (("yes", "Receive this exact Girl Asset"),),
                )
            ]
        instructions = (
            "Your actual Handler's token: "
            + token["asset"]["name"]
            + "\n"
            + token["asset"]["description"]
            + "\nReceive this exact Girl Asset; choose a slot only at the normal cap."
        )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            data["game_revision"],
            name=values.get("name", ""),
            description=values.get("description", ""),
            replace=values["replace"][0] if values.get("replace") else None,
        )
        return (
            "The exact Handler-authored token is installed."
            if result["phase"] == "complete"
            else "Your authored token is saved. Its owner now chooses any required slot."
        )

    await NativeForm(
        interaction.user.id, "Handler's Special Girl — actual token", instructions, fields, submit
    ).present(interaction)
