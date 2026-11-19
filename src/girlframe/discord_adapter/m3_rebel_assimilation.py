"""The original Handler writes and uses the group's own employment Play."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_rebel_alignment import RULE as ALIGNMENT_RULE
from girlframe.engine.m3_rebel_assimilation import EmploymentPlay
from girlframe.engine.m3_rebel_funding import RULE as FUNDING_RULE
from girlframe.services.m3_rebel_assimilation import AssimilationService


async def open_employment(
    interaction: discord.Interaction, service: AssimilationService, identity: str
) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    if data["rule"] == ALIGNMENT_RULE:
        if data["installed"]:
            await reply(
                interaction, "You are a Rebel Handler. New Rebellion rolls refer to the Foundation."
            )
            return

        async def align(click: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.install,
                viewer_from_interaction(click),
                str(click.id),
                identity,
                data["revision"],
                become_rebel=True,
                account=values["account"],
            )
            return "Your allegiance is recorded. Future Rebellion rolls refer to the Foundation."

        await NativeForm(
            interaction.user.id,
            "Become a Rebel Handler",
            "Describe your original Handler's break with the Foundation.",
            [Field("account", "Your change of allegiance", paragraph=True)],
            align,
        ).present(interaction)
        return
    if data["rule"] == FUNDING_RULE:
        if data["installed"]:
            await reply(
                interaction,
                "The original group joined the Foundation and sponsorship was recorded privately.",
            )
            return
        if not data["funding_groups"]:
            await reply(interaction, "Recover a separate active group for the original insurgency.")
            return

        async def fund(click: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.install,
                viewer_from_interaction(click),
                str(click.id),
                identity,
                data["revision"],
                funded_group=values["funded_group"][0],
                account=values["account"],
            )
            return "You have recorded the private sponsorship for future Rebellion events."

        await NativeForm(
            interaction.user.id,
            "Fund a separate insurgent group",
            "This sponsorship is private to your role.",
            [
                Field("funded_group", "Actual insurgent group", data["funding_groups"]),
                Field("account", "Your private sponsorship", paragraph=True),
            ],
            fund,
        ).present(interaction)
        return
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
