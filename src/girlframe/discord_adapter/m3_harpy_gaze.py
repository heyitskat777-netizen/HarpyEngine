"""Native original Harpy gaze and recipient-owned response controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_harpy_gaze import CHOICES, GazeService

TITLE = "Manic Pixie Dream Monster"


async def open_gaze(
    interaction: discord.Interaction,
    service: GazeService,
    channel: int,
    actor: ActorRef,
) -> None:
    data = await asyncio.to_thread(
        service.targets, viewer_from_interaction(interaction), channel, actor
    )
    if not data["targets"]:
        await reply(interaction, "There is no eligible original Girl for this gaze.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.start,
            viewer_from_interaction(current),
            str(current.id),
            channel,
            actor,
            data["revision"],
            values["target"][0],
            values["account"],
        )
        return "The original Girl’s private decision is pending."

    fields = [
        Field("target", "Actual Girl", tuple(data["targets"].items())),
        Field("account", "Describe the actual eye contact", paragraph=True),
    ]
    form = NativeForm(
        interaction.user.id,
        TITLE,
        "Choose the actual original Girl you are looking at.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_gaze_response(
    interaction: discord.Interaction,
    service: GazeService,
    identity: str,
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    step = data["step"]
    if step == "keep":
        from girlframe.discord_adapter.m2_ui import open_play

        await open_play(
            interaction,
            service.game,
            _pilot=True,
            parent=dict(
                kind="harpy_gaze_keep",
                channel=data["channel"],
                parent=None,
                body=dict(source_work=identity),
            ),
        )
        return
    if step == "void":
        if not data["assets"]:
            await reply(
                interaction, "The original Void consequence awaits an actual eligible Asset."
            )
            return
        text = "Choose the original ordinary Void gain after Keep Your Head failed."
        fields = [
            Field("choices", "Your actual eligible Asset", tuple(data["assets"].items())),
            Field("account", "Describe the change", paragraph=True),
        ]
    elif step == "choose":
        text = data["account"]
        fields = [
            Field("choices", "Two actual responses", tuple(CHOICES.items()), 2, 2),
            Field("account", "Describe what your Girl does", paragraph=True),
            Field("promise", "Write the promise if you chose it", paragraph=True, required=False),
        ]
    elif step == "break":
        text = f"Your original promise was “{data['promise']}.” Withdraw it if you back down."
        fields = [Field("confirm", "Your decision", (("break", "Withdraw the promise"),))]
    else:
        text = f"The original Girl withdrew “{data['promise']}.” You may give a Tag."
        fields = [Field("account", "The Tag you give", paragraph=True)]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            step,
            choices=tuple(values.get("choices", ())),
            account=values.get("account", ""),
            promise=values.get("promise", ""),
        )
        return "The original private choices are saved."

    form = NativeForm(interaction.user.id, TITLE, text, fields, submit)
    await reply(interaction, form.text(), form)
