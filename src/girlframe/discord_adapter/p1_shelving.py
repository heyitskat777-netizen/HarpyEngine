"""Private, reconstructable shelving intake; explicitly not a gameplay freeze."""

import asyncio
from typing import Any

import discord
from discord import app_commands

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_shelving import ShelvingService
from girlframe.services.p1_shelving_review import ShelvingReviewService

NOTICE = (
    "Intake only: no player is frozen. Activation is unavailable until safe mutation "
    "guards and shared-action recovery are implemented. Existing choices, obligations "
    "and scene locks are unchanged."
)


def request_label(row: dict[str, Any]) -> str:
    """Stable request reference plus canonical actor context, without private sheet data."""
    origin = "player request" if row["player_requested"] else "GM proposal"
    return f"Player {row['owner']} | {row['actor_context']} | {origin} | {row['id']}"


async def open_request(interaction: discord.Interaction, game: GameService, identity: str) -> None:
    service = ShelvingService(game)
    row = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    actions = []
    if row["status"] == "requested":
        if row["own"]:
            actions.append(("withdraw", "Withdraw my shelving request"))
        if row["can_review"]:
            actions.append(("verify_actor", "Check original Pilot identity (no freeze)"))
            actions.append(("decline", "Decline this request (no gameplay consequence)"))
    if not actions:
        await reply(interaction, request_label(row) + ": " + row["status"] + ". " + NOTICE)
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if values["operation"][0] == "verify_actor":
            evidence = await asyncio.to_thread(
                ShelvingReviewService(game).inspect,
                viewer_from_interaction(current),
                identity,
                row["revision"],
            )
            origin = (
                "Player request" if evidence.player_requested else "GM proposal, not player consent"
            )
            # Never render incarnation, snapshot/profile/configuration IDs or the
            # private proof. This result is an observation, never a saved permit.
            return (
                "Request " + identity + ": original Pilot identity matches current canon "
                "for this read only. " + origin + ". The request is still pending. " + NOTICE
            )
        result = await asyncio.to_thread(
            service.change,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            row["revision"],
            values["operation"][0],
        )
        return "Request " + identity + ": " + str(result["status"]) + ". " + NOTICE

    form = NativeForm(
        interaction.user.id,
        "Shelving request",
        request_label(row) + "\n" + NOTICE,
        [Field("operation", "Intake action", tuple(actions))],
        submit,
    )
    await reply(interaction, form.text(), form)


def register_shelving(tree: app_commands.CommandTree, guild_id: int, game: GameService) -> None:
    group = app_commands.Group(name="shelving", description="Shelving intake (freeze unavailable)")
    service = ShelvingService(game)

    @group.command(
        name="request", description="Request shelving for yourself; does not freeze play"
    )
    async def request(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            row = await asyncio.to_thread(
                service.request, viewer_from_interaction(interaction), str(interaction.id)
            )
            await open_request(interaction, game, row["id"])
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(name="propose", description="GM: record a shelving proposal, not player consent")
    async def propose(interaction: discord.Interaction, player: discord.Member) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            if player.bot:
                raise WorkflowError("Choose an actual player.")
            row = await asyncio.to_thread(
                service.request,
                viewer_from_interaction(interaction),
                str(interaction.id),
                player.id,
            )
            await open_request(interaction, game, row["id"])
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(name="inbox", description="Review your saved shelving intake requests")
    async def inbox(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            rows = await asyncio.to_thread(service.tasks, viewer_from_interaction(interaction))
            if not rows:
                await reply(interaction, "No pending shelving requests. " + NOTICE)
                return

            async def choose(current: discord.Interaction, values: dict[str, Any]) -> None:
                await open_request(current, game, values["request"][0])

            form = NativeForm(
                interaction.user.id,
                "Shelving intake",
                NOTICE,
                [
                    Field(
                        "request",
                        "Saved request",
                        tuple((row["id"], request_label(row)) for row in rows),
                    )
                ],
                choose,
            )
            await reply(interaction, form.text(), form)
        except WorkflowError as error:
            await reply(interaction, str(error))

    tree.add_command(group, guild=discord.Object(id=guild_id))
