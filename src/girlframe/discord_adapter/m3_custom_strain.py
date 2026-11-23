"""Author private custom Strain events from actual current tables."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_custom_strain import Design, Mode
from girlframe.engine.m3_strain_state import TRACKS
from girlframe.services.m3_custom_strain import CustomStrainService


async def open_custom(
    interaction: discord.Interaction, service: CustomStrainService, period: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.view, viewer, period)
    if not data["targets"]:
        await reply(interaction, "Introduce an eligible local NPC for this custom Strain effect.")
        return
    modes: dict[Mode, str] = {"additional": "Add an event alongside the normal rolls"}
    if data["pending"]:
        modes["instead_of_roll"] = "Use this event instead of a pending die"
    if data["rolled"]:
        modes["replace_slot"] = "Replace a slot from a saved die"

    async def open_mode(click: discord.Interaction, option: str) -> None:
        mode = next(x for x in modes if x == option)
        fields = [
            Field("title", "Event title"),
            Field("npc", "NPC who gains a Tag", data["targets"]),
            Field("tag", "Tag gained"),
            Field("account", "Describe the event", paragraph=True),
        ]
        if mode == "replace_slot":
            fields += [
                Field("work", "Choose a saved die", data["rolled"]),
                Field("column", "Column to replace", (("1", "Column 1"), ("2", "Column 2"))),
            ]
        elif mode == "instead_of_roll":
            fields.append(Field("work", "Choose an unrolled die", data["pending"]))
        else:
            fields.append(
                Field(
                    "track",
                    "Associated track, if any",
                    tuple((x, x.title()) for x in TRACKS),
                    minimum=0,
                    required=False,
                )
            )

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            work = next(iter(values.get("work", ())), None)
            selected = next(iter(values.get("column", ())), None)
            column = 1 if selected == "1" else 2 if selected == "2" else None
            track = next(iter(values.get("track", ())), None)
            result = await asyncio.to_thread(
                service.author,
                viewer_from_interaction(current),
                str(current.id),
                period,
                data["revision"],
                mode,
                Design(
                    title=values["title"].strip(),
                    account=values["account"].strip(),
                    npc=values["npc"][0],
                    tag=values["tag"].strip(),
                ),
                work=work,
                column=column,
                track=track,
            )
            if result["state"] == "registered":
                return "The slot is replaced. Choose it on the saved roll to apply the effect."
            return "The custom event took place and the NPC received the Tag."

        form = NativeForm(viewer.user_id, modes[mode], "", fields, submit)
        await reply(click, form.text(), form)

    await Picker(viewer.user_id, "Custom Strain events", tuple(modes.items()), open_mode).show(
        interaction
    )
