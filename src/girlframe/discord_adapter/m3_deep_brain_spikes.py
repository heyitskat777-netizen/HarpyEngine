"""Private acquired memory-scene setup, owned participation and printed return causes."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_deep_brain_spikes import DeepBrainSpikesService
from girlframe.services.onboarding import WorkflowError


async def open_spikes(
    interaction: discord.Interaction,
    service: DeepBrainSpikesService,
    identity: str | None = None,
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), identity)
    if data["kind"] == "acquisition":
        if data["acquisition"] is None:
            if not data["awards"]:
                await reply(
                    interaction, "No actual held advancement is available for Deep-Brain-Spikes."
                )
                return

            async def buy(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.buy,
                    viewer_from_interaction(current),
                    str(current.id),
                    values["award"][0],
                    data["revision"],
                    values["account"],
                )
                return "Deep-Brain-Spikes acquired. Use its History card in a scene."

            await NativeForm(
                interaction.user.id,
                "Acquire Deep-Brain-Spikes",
                "Spend one held advancement on your memory-scene ability.",
                [
                    Field(
                        "award",
                        "Actual held source award",
                        tuple((x["id"], clean(x["label"])[:100]) for x in data["awards"]),
                    ),
                    Field("account", "Actual acquisition", paragraph=True),
                ],
                buy,
            ).present(interaction)
            return
        if data["active"]:
            await open_spikes(interaction, service, data["active"][0]["id"])
            return
        scenes = [x for x in data["scenes"] if x["girls"]]
        if not scenes:
            await reply(
                interaction, "Join an actual ordinary scene with its current original Girl first."
            )
            return

        async def choose_scene(current: discord.Interaction, values: dict[str, Any]) -> str | None:
            scene = next(x for x in scenes if x["scene"] == values["scene"][0])

            async def begin(followup: discord.Interaction, fields: dict[str, Any]) -> str:
                girl = next(x["ref"] for x in scene["girls"] if x["token"] == fields["subject"][0])
                result = await asyncio.to_thread(
                    service.begin,
                    viewer_from_interaction(followup),
                    str(followup.id),
                    data["acquisition"],
                    data["revision"],
                    scene["channel"],
                    ActorRef.model_validate(girl),
                    fields["mode"][0],
                    fields["period"][0],
                    fields["beginning"],
                    fields["circumstances"],
                )
                return (
                    "Memory scene active in channel "
                    + str(scene["channel"])
                    + ". Play normally there; "
                    "its private History card opens participation and return controls. Source: "
                    + str(result["id"])
                )

            await NativeForm(
                current.user.id,
                "Set the played memory's beginning",
                "Set a scene that happened offscreen or before the game. Participants own their "
                "speech/actions. Remembered fiction does not rewrite current facts or move bodies.",
                [
                    Field(
                        "subject",
                        "Actual memory subject",
                        tuple((x["token"], x["label"]) for x in scene["girls"]),
                    ),
                    Field(
                        "mode",
                        "Your memory-scene perspective",
                        (
                            ("there", "I am there in the played memory"),
                            ("watching", "I watch it happen"),
                        ),
                    ),
                    Field(
                        "period",
                        "Actual memory scope",
                        (
                            ("offscreen", "A scene that happened offscreen"),
                            ("before_game", "A scene before the game began"),
                        ),
                    ),
                    Field("beginning", "Set the memory scene's beginning", paragraph=True),
                    Field(
                        "circumstances", "Current circumstances this may illuminate", paragraph=True
                    ),
                ],
                begin,
            ).present(current)
            return None

        await NativeForm(
            interaction.user.id,
            "Choose the actual present scene",
            "Memory becomes this channel's real scene context, preserving the present reference. "
            "No past world or historical character sheet is reconstructed.",
            [
                Field(
                    "scene",
                    "Joined ordinary scene",
                    tuple((x["scene"], "Scene in channel " + str(x["channel"])) for x in scenes),
                )
            ],
            choose_scene,
        ).present(interaction)
        return
    summary = (
        "Played memory in channel "
        + str(data["channel"])
        + "; saved present "
        + data["present_scene"]
        + ".\nBeginning: "
        + clean(data["beginning"])
        + "\nCurrent circumstances: "
        + clean(data["circumstances"])
    )
    if data["phase"] == "returned":
        await reply(
            interaction,
            summary
            + "\nReturned because "
            + str(data["return_cause"])
            + ": "
            + clean(data["return_account"] or ""),
        )
        return
    operations: tuple[tuple[str, str], ...] = (
        ("contribute", "Record my actual remembered speech/action"),
    )
    if data["owner"]:
        operations += (("return", "Record printed cause and return to the present"),)

    async def act(current: discord.Interaction, values: dict[str, Any]) -> str:
        if values["operation"][0] == "return":
            if not values.get("cause"):
                raise WorkflowError("Choose the actual relevance or major-discrepancy return cause")
            await asyncio.to_thread(
                service.return_present,
                viewer_from_interaction(current),
                str(current.id),
                data["id"],
                data["revision"],
                values["cause"][0],
                values["account"],
            )
            return "Returned to the saved present scene. Real intervening Play effects remain real."
        await asyncio.to_thread(
            service.contribute,
            viewer_from_interaction(current),
            str(current.id),
            data["id"],
            data["revision"],
            values["account"],
            values.get("action") or None,
        )
        return (
            "Your actual memory-scene contribution saved privately. Continue normal Conversation."
        )

    fields = [
        Field("operation", "Actual memory-scene action", operations),
        Field("account", "Your speech/action or actual return reason", paragraph=True),
        Field("action", "Your completed current-actor Play ID, if applicable", required=False),
    ]
    if data["owner"]:
        fields.append(
            Field(
                "cause",
                "Actual printed return cause (for return only)",
                (
                    ("relevance_clear", "The memory's relation to present circumstances is clear"),
                    ("major_discrepancy", "Discrepancies are too major to ignore"),
                ),
                0,
                1,
                required=False,
            )
        )
    await NativeForm(
        interaction.user.id,
        "Play the memory normally",
        summary
        + "\nUse normal Conversation in that scene. Only genuine legal current-actor Plays affect "
        "current resources. Return when relevance is clear or discrepancies become too major.",
        fields,
        act,
    ).present(interaction)
