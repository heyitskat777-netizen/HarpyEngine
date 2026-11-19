"""Private native controls for a joined fictional Director's phone powers."""

import asyncio
from typing import Any, Literal

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_custom_strain import Slot
from girlframe.engine.m3_director_strain import DIRECT_EVENTS, Command
from girlframe.engine.m3_strain_catalog import ROWS
from girlframe.engine.m3_strain_state import TRACKS
from girlframe.services.m3_director_strain import DirectorStrainService


async def open_phone(
    interaction: discord.Interaction,
    service: DirectorStrainService,
    channel: int,
    sender: ActorRef,
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.view, viewer, channel, sender)
    modes: dict[Literal["severity", "trigger"], str] = {"severity": "Set a track High or Low"}
    if data["period"]:
        modes["trigger"] = "Trigger a Strain event"
    track_options = tuple((x, x.title()) for x in TRACKS)

    async def open_mode(click: discord.Interaction, choice: str) -> None:
        mode = next(x for x in modes if x == choice)
        if mode == "severity":
            fields = [
                Field("track", "Strain track", track_options),
                Field("severity", "New level", (("low", "Low"), ("high", "High"))),
            ]
        else:
            choices = []
            for identity in sorted(DIRECT_EVENTS):
                _, track, level, face, column = identity.split(".")
                slot = Slot.model_validate(
                    dict(track=track, severity=level, face=int(face), column=int(column))
                )
                text = ROWS[slot.track, slot.severity][slot.face - 1][slot.column - 1]
                choices.append(
                    (identity, f"{track.title()} {level.title()} {face}.{column} · {text}")
                )
            fields = [Field("event", "Event to trigger", tuple(choices))]
        fields.append(Field("account", "What do you tell the Handler?", paragraph=True))

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            slot_data = None
            if mode == "trigger":
                _, track, severity, face, column = values["event"][0].split(".")
                slot_data = dict(track=track, severity=severity, face=int(face), column=int(column))
            else:
                track, severity = values["track"][0], values["severity"][0]
            result = await asyncio.to_thread(
                service.call,
                viewer_from_interaction(current),
                str(current.id),
                channel,
                data["revision"],
                sender,
                Command.model_validate(
                    dict(
                        mode=mode,
                        track=track,
                        severity=severity,
                        slot=slot_data,
                        account=values["account"],
                    )
                ),
            )
            if result["effect"]:
                return (
                    "The call was filed. The actual effect remains required in the Handler’s Inbox."
                )
            return "The track’s level changed. Previously saved dice keep their original tables."

        await NativeForm(viewer.user_id, modes[mode], "", fields, submit).present(click)

    await Picker(viewer.user_id, "Call the Handler", tuple(modes.items()), open_mode).show(
        interaction
    )


async def open_phone_receipt(
    interaction: discord.Interaction, service: DirectorStrainService, identity: str
) -> None:
    call = await asyncio.to_thread(service.receipt, viewer_from_interaction(interaction), identity)
    await reply(interaction, "**Director’s call**\n" + clean(call.command.account))
