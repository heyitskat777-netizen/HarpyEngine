"""The original Handler writes and uses the group's own employment Play."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_rebel_assimilation import EmploymentPlay
from girlframe.services.m3_rebel_assimilation import AssimilationService


async def open_employment(
    interaction: discord.Interaction, service: AssimilationService, identity: str
) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    if not data["installed"]:

        async def write(click: discord.Interaction, values: dict[str, Any]) -> str:
            play = EmploymentPlay.model_validate(
                {k: values[k] for k in ("title", "trigger", "result")}
            )
            await asyncio.to_thread(
                service.install,
                viewer_from_interaction(click),
                str(click.id),
                identity,
                data["revision"],
                play,
            )
            return "The group joined the Foundation. The new Play is available in your Inbox."

        await NativeForm(
            interaction.user.id,
            "Write the group's employment Play",
            "Describe what you now do for " + clean(data["group"]) + ".",
            [
                Field("title", "Play name"),
                Field("trigger", "When can you make this Play?", paragraph=True),
                Field("result", "What work do you perform?", paragraph=True),
            ],
            write,
        ).present(interaction)
        return

    play = data["play"]
    channel = int(interaction.channel_id or 0)
    if play is None:
        await reply(interaction, "The original group has entered the Foundation.")
        return

    async def use(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.use,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            channel,
            trigger_met=values["trigger_met"] == ("yes",),
            account=values["account"],
        )
        return "Your work in the original scene is recorded."

    await NativeForm(
        interaction.user.id,
        play.title,
        "\n\n".join((clean(play.trigger), clean(play.result))),
        [
            Field(
                "trigger_met", "Actual trigger", (("yes", "The trigger occurred in this scene"),)
            ),
            Field("account", "What did you do?", paragraph=True),
        ],
        use,
    ).present(interaction)
