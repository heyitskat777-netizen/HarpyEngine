"""A real Keep Your Head child, or a standalone resistance in an actual joined scene."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_void_keep import start_view
from girlframe.services.onboarding import WorkflowError


async def open_keep(interaction: discord.Interaction, game: GameService, identity: str) -> None:
    data = await asyncio.to_thread(start_view, game, viewer_from_interaction(interaction), identity)
    if data["child"]:
        if data["choice"]:
            from girlframe.discord_adapter.m2_ui import open_choice

            await open_choice(interaction, game, data["choice"])
        else:
            await reply(
                interaction, "Your actual resistance is saved and awaits its next owned response."
            )
        return
    if data["stage"] != "resist_pending":
        raise WorkflowError(
            "Continue the actual Void request's current stage instead of rerolling."
        )
    if not data["channels"]:
        raise WorkflowError("Join an actual bound scene with the Handler before this resistance.")
    from girlframe.discord_adapter.m3_dampener import fields as dampener_fields
    from girlframe.discord_adapter.m3_dampener import modifier as dampener_modifier
    from girlframe.services.m3_dampener import DampenerService

    dampener_controls = await dampener_fields(
        interaction, DampenerService(game), ActorRef.model_validate(data["actor"])
    )
    fields = [
        Field(
            "heat",
            "Heat for this actual Keep Your Head",
            tuple(
                (str(x), str(x))
                for x in ((data["heat"],) if data["heat"] >= 5 else range(data["heat"] + 1))
            ),
        ),
        Field("account", "Actual resistance to the Frame's Void", paragraph=True),
    ] + dampener_controls
    channel = (
        interaction.channel_id
        if interaction.channel_id in data["channels"]
        else data["channels"][0]
        if len(data["channels"]) == 1
        else None
    )
    if channel is None:
        options = []
        for index, identity_channel in enumerate(data["channels"]):
            cached = interaction.guild.get_channel(identity_channel) if interaction.guild else None
            options.append(
                (str(identity_channel), getattr(cached, "name", "Joined scene " + str(index + 1)))
            )
        fields.insert(0, Field("scene", "Actual joined scene", tuple(options)))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            game.begin,
            viewer_from_interaction(current),
            str(current.id),
            channel if channel is not None else int(values["scene"][0]),
            data["sheet_revision"],
            PlayInput(
                play="keep_your_head",
                heat=int(values["heat"][0]),
                dampener_modifier=dampener_modifier(values),
                context=values["account"],
                trigger_confirmed=True,
                parent=data["parent"],
                source_work=identity,
            ),
        )
        return "Actual resistance reserved. Resume its owned choices. Action: " + str(
            result["action_id"]
        )

    form = NativeForm(
        interaction.user.id,
        "Resist the Frame's Void",
        "Make an actual Keep Your Head. Prevention requires in control and the Handler's "
        "actual sufficient-result ruling. Failed resistance keeps this chat paused for the "
        "remaining owned Void choices.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)
