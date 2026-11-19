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
from girlframe.engine.m3_custom_strain import Design, Slot
from girlframe.engine.m3_director_strain import DIRECT_EVENTS, Command
from girlframe.engine.m3_named_strain import Design as TrackDesign
from girlframe.engine.m3_named_strain import Option
from girlframe.engine.m3_strain_catalog import ROWS
from girlframe.engine.m3_strain_state import TRACKS
from girlframe.services.m3_director_strain import DirectorStrainService
from girlframe.services.onboarding import WorkflowError


def track_design(name: str, npc: str, raw: str) -> TrackDesign:
    rows = []
    for line in raw.strip().splitlines():
        parts = [x.strip() for x in line.split("|")]
        if len(parts) != 4 or not all(parts):
            raise WorkflowError("Enter a title and Tag for each column on every face.")
        rows.append((Option(title=parts[0], tag=parts[1]), Option(title=parts[2], tag=parts[3])))
    if len(rows) != 6:
        raise WorkflowError("Enter six lines in die-face order.")
    return TrackDesign(name=name.strip(), npc=npc, faces=tuple(rows))


async def open_phone(
    interaction: discord.Interaction,
    service: DirectorStrainService,
    channel: int,
    sender: ActorRef,
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.view, viewer, channel, sender)
    modes: dict[Literal["severity", "trigger", "replace", "create_track"], str] = {
        "severity": "Set a track High or Low"
    }
    if data["period"]:
        modes["trigger"] = "Trigger a Strain event"
    if data["targets"]:
        modes["replace"] = "Write a replacement Strain event"
        modes["create_track"] = "Create and roll a new Strain track"
    track_options = tuple((x, x.title()) for x in TRACKS)

    async def open_mode(click: discord.Interaction, choice: str) -> None:
        mode = next(x for x in modes if x == choice)
        if mode == "severity":
            fields = [
                Field("track", "Strain track", track_options),
                Field("severity", "New level", (("low", "Low"), ("high", "High"))),
            ]
        elif mode == "create_track":
            fields = [
                Field("name", "New track name"),
                Field("npc", "Known NPC who gains the selected Tag", data["targets"]),
                Field("faces", "Six pairs of events and Tags", paragraph=True),
            ]
        else:
            choices = []
            events = (
                sorted(DIRECT_EVENTS)
                if mode == "trigger"
                else [
                    f"strain.{track}.{level}.{face}.{column}"
                    for track, level in ROWS
                    for face in range(1, 7)
                    for column in (1, 2)
                ]
            )
            for identity in events:
                _, track, level, face, column = identity.split(".")
                slot = Slot.model_validate(
                    dict(track=track, severity=level, face=int(face), column=int(column))
                )
                text = ROWS[slot.track, slot.severity][slot.face - 1][slot.column - 1]
                choices.append(
                    (identity, f"{track.title()} {level.title()} {face}.{column} · {text}")
                )
            fields = [
                Field(
                    "event",
                    "Printed slot to replace" if mode == "replace" else "Event to trigger",
                    tuple(choices),
                )
            ]
            if mode == "replace":
                fields += [
                    Field("title", "New event title"),
                    Field("npc", "Known NPC who gains a Tag", data["targets"]),
                    Field("tag", "Tag gained"),
                ]
        fields.append(Field("account", "What do you tell the Handler?", paragraph=True))

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            slot_data = None
            design = None
            new_track = None
            if mode in ("trigger", "replace"):
                _, track, severity, face, column = values["event"][0].split(".")
                slot_data = dict(track=track, severity=severity, face=int(face), column=int(column))
            elif mode == "severity":
                track, severity = values["track"][0], values["severity"][0]
            else:
                track, severity = None, None
                new_track = track_design(values["name"], values["npc"][0], values["faces"])
            if mode == "replace":
                design = Design(
                    title=values["title"].strip(),
                    tag=values["tag"].strip(),
                    npc=values["npc"][0],
                    account=values["account"].strip(),
                )
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
                        design=design,
                        new_track=new_track,
                    )
                ),
            )
            if mode == "replace":
                return "The replacement takes effect when the Handler chooses this slot."
            if mode == "create_track":
                return f"The new track rolled {result['face']}. The Handler owns its column choice."
            if result["effect"]:
                return (
                    "The call was filed. The actual effect remains required in the Handler’s Inbox."
                )
            return "The track’s level changed. Previously saved dice keep their original tables."

        instructions = (
            "Enter one line per die face, in order from 1 to 6. Use four fields per line:\n"
            "`Title 1 | Tag 1 | Title 2 | Tag 2`"
            if mode == "create_track"
            else ""
        )
        await NativeForm(viewer.user_id, modes[mode], instructions, fields, submit).present(click)

    await Picker(viewer.user_id, "Call the Handler", tuple(modes.items()), open_mode).show(
        interaction
    )


async def open_phone_receipt(
    interaction: discord.Interaction, service: DirectorStrainService, identity: str
) -> None:
    call = await asyncio.to_thread(service.receipt, viewer_from_interaction(interaction), identity)
    await reply(interaction, "**Director’s call**\n" + clean(call.command.account))
