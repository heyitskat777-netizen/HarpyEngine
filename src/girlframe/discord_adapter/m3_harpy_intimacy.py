"""Native private invitation, consent, escape and Harpy source consequences."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_harpy_intimacy import HarpyIntimacyService

TITLE = "Harpy intimacy"


async def open_intimacy(
    interaction: discord.Interaction, service: HarpyIntimacyService, channel: int, actor: ActorRef
) -> None:
    data = await asyncio.to_thread(
        service.menu, viewer_from_interaction(interaction), channel, actor
    )
    people = tuple(data["people"].items())
    if not people:
        await reply(interaction, "There is no eligible original local participant.")
        return

    async def invite(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.offer,
            viewer_from_interaction(click),
            str(click.id),
            channel,
            actor,
            data["revision"],
            values["person"][0],
        )
        return "The original participant has a private consent request."

    form = NativeForm(
        interaction.user.id,
        TITLE,
        "Invite the original participant to decide privately.",
        [Field("person", "Actual original person", people)],
        invite,
    )
    await reply(interaction, form.text(), form)


async def open_intimacy_choice(
    interaction: discord.Interaction, service: HarpyIntimacyService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    step = data["step"]
    fields: list[Field] = []
    options: tuple[tuple[str, str], ...]
    if step == "consent":
        text = "Choose whether to participate in this private encounter."
        options = (("accept", "Accept"), ("decline", "Decline"))
    elif step == "escape":
        text = "You own your response to the encounter."
        options = (
            ("keep", "Attempt to escape with Keep Your Head"),
            ("stay", "Forgo the escape attempt"),
            ("withdraw", "Withdraw consent"),
        )
    elif step == "rebirth":
        text = "Begin the original Apometanoia with your Frame."
        options = (("begin", "Open the original transformation"),)
    else:
        text = "Choose and describe your actual ordinary Void gain."
        options = tuple(data["assets"].items())
        fields.append(Field("account", "Describe the Asset’s change", paragraph=True))
    if not options:
        await reply(interaction, "The original consequence requires an eligible owned Asset.")
        return

    async def confirm(click: discord.Interaction, values: dict[str, Any]) -> str | None:
        choice = values["choice"][0]
        if step == "escape" and choice == "keep":
            from girlframe.discord_adapter.m2_ui import open_play

            await open_play(
                click,
                service.game,
                _pilot=True,
                parent=dict(
                    kind="harpy_private_keep",
                    channel=data["channel"],
                    parent=None,
                    body=dict(source_work=identity),
                ),
            )
            return None
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            step,
            choice,
            values.get("account", ""),
        )
        return "Your original private decision is saved."

    form = NativeForm(
        interaction.user.id,
        TITLE,
        text,
        [Field("choice", "Your decision", options), *fields],
        confirm,
    )
    await reply(interaction, form.text(), form)
