"""Private world-facilitator choices and explicit NPC Attack confirmation."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_gorgon import NpcAttack
from girlframe.services.m3_gorgon import GorgonService


async def open_gorgon_attack(interaction: discord.Interaction, service: GorgonService) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.preview, viewer)
    attackers = {x["token"]: x for x in data["attackers"]}
    if not attackers:
        await reply(
            interaction,
            "No eligible Gorgon/NPC Attack is available in the recorded world. "
            "This branch supports co-located ordinary NPCs. Benevolent Gorgons cannot Attack; "
            "dormancy, special NPC deaths and other target branches still need their resolvers.",
        )
        return

    async def select(current: discord.Interaction, token: str) -> None:
        attacker = attackers[token]
        targets = {x["token"]: x for x in attacker["targets"]}

        async def submit(response: discord.Interaction, values: dict[str, Any]) -> str:
            target = targets[values["target"][0]]
            result = await asyncio.to_thread(
                service.attack,
                viewer_from_interaction(response),
                str(response.id),
                data["game_revision"],
                NpcAttack(
                    attacker=ActorRef.model_validate(attacker["ref"]),
                    target=ActorRef.model_validate(target["ref"]),
                    assets=tuple(values["assets"]),
                    attacker_sha256=attacker["source_sha256"],
                    target_sha256=target["source_sha256"],
                    account=values["account"],
                    trigger_confirmed=True,
                ),
            )
            return (
                "The actual NPC's death is recorded. No player character's resources changed. "
                "Saved Attack: " + str(result["id"])
            )

        form = NativeForm(
            viewer.user_id,
            "Confirm Gorgon Attack on an NPC",
            "Attacker: " + clean(attacker["label"]) + ". Choose its actual attacking Assets "
            "and the reachable NPC. This Attack kills that NPC. Record the actual action in "
            "the Conversation before confirming. Private world details stay in this review.",
            [
                Field(
                    "target",
                    "Actual NPC target",
                    tuple((k, x["label"]) for k, x in targets.items()),
                ),
                Field(
                    "assets",
                    "Attacking Gorgon Assets",
                    tuple((x["id"], x["name"]) for x in attacker["assets"]),
                    1,
                    min(25, len(attacker["assets"])),
                ),
                Field("account", "Actual attack and why its Assets reach the NPC", paragraph=True),
                Field(
                    "confirm",
                    "Confirm the printed consequence",
                    (("yes", "Attack and kill the selected NPC"),),
                ),
            ],
            submit,
        )
        await reply(current, form.text(), form)

    await Picker(
        viewer.user_id,
        "**Gorgon Attack — ordinary NPCs**\nChoose the actual attacking Gorgon.",
        tuple((k, x["label"]) for k, x in attackers.items()),
        select,
    ).show(interaction)
