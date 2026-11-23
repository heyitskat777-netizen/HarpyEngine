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
from girlframe.services.m3_erratic_gorgon import ErraticService
from girlframe.services.m3_gorgon import GorgonService
from girlframe.services.onboarding import WorkflowError


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
            outcome = (
                "The actual NPC is kept alive by existing Metal Angel care. "
                if result["outcome"] == "npc_kept_alive"
                else "The actual NPC's death is recorded. "
            )
            return (
                outcome
                + "No player character's resources changed. Saved Attack: "
                + str(result["id"])
            )

        form = NativeForm(
            viewer.user_id,
            "Confirm Gorgon Attack on an NPC",
            "Attacker: " + clean(attacker["label"]) + ". Choose its actual attacking Assets "
            "and the reachable NPC. This Attack is lethal unless actual Metal Angel care "
            "keeps that NPC alive. Record the actual action in "
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
                    (("yes", "Resolve the lethal Attack on the selected NPC"),),
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


async def open_erratic_tag(interaction: discord.Interaction, service: ErraticService) -> None:
    viewer = viewer_from_interaction(interaction)
    if interaction.channel_id is None:
        await reply(interaction, "Open this control from the Erratic Gorgon's joined scene.")
        return
    channel = interaction.channel_id
    data = await asyncio.to_thread(service.view, viewer, channel)
    if not data["gorgons"] or not data["npcs"]:
        await reply(interaction, "Join with an actual Erratic Gorgon and recover an eligible NPC.")
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.tag,
            viewer_from_interaction(click),
            str(click.id),
            channel,
            data["revision"],
            values["gorgon"][0],
            values["npc"][0],
            values["tag"],
            values["account"],
        )
        return "The actual NPC's Tag is recorded."

    form = NativeForm(
        viewer.user_id,
        "Inflict an Erratic Gorgon Tag",
        "Record the actual NPC consequence.",
        [
            Field("gorgon", "Original Erratic Gorgon", data["gorgons"]),
            Field("npc", "Actual NPC", data["npcs"]),
            Field("tag", "Tag"),
            Field("account", "What caused it?", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_erratic_flight(
    interaction: discord.Interaction, service: ErraticService, *, pursuit: bool
) -> None:
    channel = interaction.channel_id
    if channel is None:
        raise WorkflowError("Open the Erratic Gorgon's actual battlefield scene")
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.flight_view, viewer, channel)
    cases = data["pursuits" if pursuit else "battles"]
    if not cases:
        raise WorkflowError(
            "Use a completed Engage advance or pin"
            if pursuit
            else "Finish an actual exchange with your Erratic Gorgon first"
        )
    options = {str(i): case for i, case in enumerate(cases)}
    fields = [
        Field(
            "case",
            "Original battle or pursuit",
            tuple(
                (key, case.get("label", "Original Engage " + case["action"][:8]))
                for key, case in options.items()
            ),
        )
    ]
    if not pursuit:
        fields.extend(
            [
                Field("x", "Destination X"),
                Field("y", "Destination Y"),
                Field("account", "How the Gorgon escapes the battle", paragraph=True),
            ]
        )

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        case = options[values["case"][0]]
        args = (viewer_from_interaction(click), str(click.id), channel, data["revision"])
        if pursuit:
            await asyncio.to_thread(service.catch, *args, case["event"], case["action"])
            return "The original pursuit caught the Erratic Gorgon."
        try:
            destination = (int(values["x"]), int(values["y"]))
        except ValueError as exc:
            raise WorkflowError("Enter actual mapped X and Y coordinates") from exc
        await asyncio.to_thread(
            service.flee, *args, case["gorgon"], case["action"], destination, values["account"]
        )
        return "Flight applied to the original Gorgon. Pursuit is open."

    form = NativeForm(
        viewer.user_id,
        "Catch the Erratic Gorgon" if pursuit else "Erratic Gorgon flight",
        "Use the actual completed battle or pursuit in this scene.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)
