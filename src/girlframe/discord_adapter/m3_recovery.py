"""Owned native recovery of an actual interrupted shared-Play response chain."""

from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm, threaded
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m2_game import GameService
from girlframe.services.m3_recovery import RecoveryService


async def open_recovery(
    interaction: discord.Interaction, game: GameService, saved: dict[str, Any]
) -> None:
    options: tuple[tuple[str, str], ...] = (("resume", "Resume the saved response chain"),)
    if saved["cancellable"]:
        options += (("cancel", "Cancel this unanswered, unrolled reservation"),)

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await threaded(
            lambda: RecoveryService(game).recover(
                viewer_from_interaction(current),
                str(current.id),
                saved["id"],
                saved["revision"],
                cancel=values["operation"] == ("cancel",),
            )
        )
        return (
            "Unanswered, unrolled reservation cancelled. No resources were refunded."
            if result["cancelled_unrolled"]
            else "Saved responses restored. Chat will pause again; the original dice, "
            "spending and prior answers remain. Reopen /choice resume."
        )

    form = NativeForm(
        interaction.user.id,
        "Recover your saved Play",
        "Staff must restore chat before recovery. "
        + (
            "This chain includes a known roll, which cannot be discarded or repeated. "
            if saved["rolled"]
            else "No dice are recorded in this chain. "
        )
        + str(saved["descendants"])
        + " saved child response(s). "
        "Each original player keeps their own decisions.",
        [Field("operation", "Recovery", options)],
        submit,
    )
    await reply(interaction, form.text(), form)
