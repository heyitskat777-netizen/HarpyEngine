"""Owned NPC Bond request and original NPC human's addressed Conversation rendition."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_npc_bond_play import NpcBondPlayService


async def open_npc_bond_play(
    interaction: discord.Interaction, service: NpcBondPlayService, identity: str | None = None
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), identity)
    user = viewer_from_interaction(interaction).user_id
    if data["control"]:
        moves = {
            row["token"] + ":" + move["job"]: (row, move)
            for row in data["npcs"]
            for move in row["moves"]
        }
        if not moves:
            await reply(
                interaction,
                "No current NPC Bond offers an implemented Conversation move.",
            )
            return

        async def request(current: discord.Interaction, values: dict[str, Any]) -> str:
            npc, move = moves[values["move"][0]]
            result = await asyncio.to_thread(
                service.request,
                viewer_from_interaction(current),
                str(current.id),
                data["revision"],
                ActorRef.model_validate(npc["ref"]),
                move["job"],
                move["move"],
                values["context"],
            )
            return "NPC Bond weakened. The NPC's human has its Play in Requests. Reference: " + str(
                result["id"]
            )

        form = NativeForm(
            user,
            "Weaken your NPC Bond — request an actual Play",
            "Choose a real job-defined Conversation move. Personal is "
            "erased; Intense becomes Personal. Your NPC's human authors the actual Play.",
            [
                Field(
                    "move",
                    "NPC and actual printed move",
                    tuple(
                        (key, clean(row["label"]) + " — " + move["move"])
                        for key, (row, move) in moves.items()
                    ),
                ),
                Field("context", "What actual intervention are you requesting?", paragraph=True),
            ],
            request,
        )
        await reply(interaction, form.text(), form)
        return
    lines = [
        "**NPC Conversation Play — " + clean(data["move"]) + "**",
        "Original NPC: " + clean(data["npc"]["label"]),
        "Actual performance complete."
        if data["phase"] == "complete"
        else "Waiting for the NPC's actual human rendition.",
    ]
    if data["cost"]:
        lines.insert(
            2, "Bond cost: " + str(data["cost"]["before"]) + " → " + str(data["cost"]["after"])
        )
    if data["context"]:
        lines.append(clean(data["context"]))
    if data["rendition"]:
        lines.append(clean(data["rendition"]))
    if data["stale"]:
        lines.append(clean(data["stale"]))
    if not data["can_perform"]:
        await reply(interaction, "\n\n".join(lines)[:1950])
        return
    scenes = {x["id"]: x for x in data["scenes"] if x["recipients"]}
    if not scenes:
        await reply(
            interaction,
            "\n\n".join(lines)
            + "\nJoin this NPC and its real recipients to a scene before performing.",
        )
        return

    async def choose(current: discord.Interaction, channel: str) -> None:
        scene = scenes[channel]
        recipients = {x["token"]: x for x in scene["recipients"]}

        async def perform(actual: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.perform,
                viewer_from_interaction(actual),
                str(actual.id),
                data["id"],
                data["revision"],
                int(channel),
                tuple(ActorRef.model_validate(recipients[x]["ref"]) for x in values["recipients"]),
                values["rendition"],
            )
            return "NPC rendition saved for its addressed audience. Source work complete."

        form = NativeForm(
            user,
            "Perform the NPC's actual " + data["move"],
            "Write the NPC's actual words/actions, not an acknowledgment. "
            "This is a Conversation move. Other effects need their actual source controls.",
            [
                Field(
                    "recipients",
                    "Actual addressed scene recipients",
                    tuple((key, clean(x["label"])) for key, x in recipients.items()),
                    maximum=len(recipients),
                ),
                Field("rendition", "NPC's actual speech / concrete performance", paragraph=True),
            ],
            perform,
        )
        await reply(current, form.text(), form)

    await reply(
        interaction,
        "\n\n".join(lines)[:1900],
        Picker(
            user,
            "Actual performance scene",
            tuple((key, x["label"]) for key, x in scenes.items()),
            choose,
        ),
    )
