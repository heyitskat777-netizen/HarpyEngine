"""Owned dropdown declarations for printed, diceless Gorgon Plays."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_gorgon_play_state import Declaration
from girlframe.services.m2_game import GameService
from girlframe.services.m3_gorgon_play import GorgonPlayService


async def open_gorgon_play(interaction: discord.Interaction, game: GameService) -> None:
    service = GorgonPlayService(game)
    channel = int(interaction.channel_id or 0)
    data = await asyncio.to_thread(service.preview, viewer_from_interaction(interaction), channel)
    own = [x for x in data["actors"] if x["owned"] and x["ref"]["kind"] == "gorgon"]
    if not own or not data["plays"]:
        await reply(interaction, "No reviewed Gorgon Play is available for your actual scene role.")
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str:
        actor = next(x for x in own if x["token"] == values["actor"][0])
        kind = values["play"][0]
        targets = [x for x in data["actors"] if x["ref"] != actor["ref"]]
        if kind == "attack" and not targets:
            return "Join the actual opposing body to the scene before declaring an Attack."
        if kind != "warp" and not actor["assets"]:
            return "Declare actual owned Gorgon Assets for this Play."
        fields: list[Field] = []
        if kind == "attack":
            fields.append(
                Field(
                    "target",
                    "Actual opposing body",
                    tuple((x["token"], x["label"]) for x in targets),
                )
            )
        if kind != "warp":
            fields.append(
                Field(
                    "assets",
                    "Your actual Assets used",
                    tuple(
                        (x["id"], x["name"] + (" (damaged; judge review)" if x["damaged"] else ""))
                        for x in actor["assets"]
                    ),
                    maximum=len(actor["assets"]),
                )
            )
        fields.extend(
            [
                Field("account", "Describe the action and actual reach", paragraph=True),
                Field(
                    "reach",
                    "Confirm the actual physical declaration",
                    (("confirmed", "Confirm declared reach; judge resolves uncertainty"),),
                ),
            ]
        )

        async def declare(next_interaction: discord.Interaction, details: dict[str, Any]) -> str:
            target = (
                next(x for x in targets if x["token"] == details["target"][0])
                if kind == "attack"
                else None
            )
            result = await asyncio.to_thread(
                service.begin,
                viewer_from_interaction(next_interaction),
                str(next_interaction.id),
                channel,
                data["revision"],
                Declaration(
                    kind=kind,
                    actor=ActorRef.model_validate(actor["ref"]),
                    assets=tuple(details.get("assets", ())),
                    actor_sha256=actor["source_sha256"],
                    target=ActorRef.model_validate(target["ref"]) if target else None,
                    target_sha256=target["source_sha256"] if target else None,
                    account=details["account"],
                    reach_confirmed=True,
                ),
            )
            return (
                "Declaration saved. Scene chat locks before the actual choices and effects. "
                "No Gorgon dice are rolled. Pending responses are in /choice resume. Action `"
                + str(result["action_id"])
                + "`."
            )

        form = NativeForm(
            interaction.user.id,
            "Declare Gorgon " + kind,
            "Choose the actual resources and physical target. "
            "Required human responses remain owned.",
            fields,
            declare,
        )
        await reply(current, form.text(), form)
        return "Complete the new private declaration."

    form = NativeForm(
        interaction.user.id,
        "Gorgon Plays",
        "Use your actual scene role. These Plays have no Gorgon roll or Heat spend.",
        [
            Field("actor", "Your actual Gorgon", tuple((x["token"], x["label"]) for x in own)),
            Field("play", "Choose your Play", tuple((x, x.title()) for x in data["plays"])),
        ],
        choose,
    )
    await reply(interaction, form.text(), form)
