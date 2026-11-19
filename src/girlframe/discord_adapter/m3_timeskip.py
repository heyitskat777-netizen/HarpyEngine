"""Private native Timeskip approval and ordered world controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.m3_world import TYPES, coordinates
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_timeskip import DURATIONS, Arrival, TimeskipService


async def open_timeskip_start(interaction: discord.Interaction, service: TimeskipService) -> None:
    revision = await asyncio.to_thread(service.start_menu, viewer_from_interaction(interaction))

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.start,
            viewer_from_interaction(click),
            str(click.id),
            revision,
            int(values["duration"][0]),
        )
        return "The table can consider the proposed duration in the private Inbox."

    form = NativeForm(
        interaction.user.id,
        "Propose a Timeskip",
        "Each current player receives their own decision about the proposed duration.",
        [
            Field(
                "duration",
                "Printed length of time",
                tuple((str(k), v) for k, v in DURATIONS.items()),
            )
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_timeskip(
    interaction: discord.Interaction, service: TimeskipService, case: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), case)
    step = data["step"]
    title = "Timeskip · " + data["duration"]
    if step == "agreement" and data.get("accepted"):
        await reply(interaction, "The Timeskip is waiting for the original table's decisions.")
        return
    if step == "declined":
        await reply(interaction, "The table declined this Timeskip.")
        return
    if step == "newgirl":
        await reply(
            interaction,
            "World changes are saved. The next step is the original Newgirl’s playbook.",
        )
        return
    if step == "agreement":
        fields = [
            Field("vote", "Your decision", (("accept", "Agree"), ("decline", "Decline"))),
        ]

        async def vote(click: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.vote,
                viewer_from_interaction(click),
                str(click.id),
                case,
                data["revision"],
                values["vote"][0] == "accept",
            )
            return "Your decision is saved."

        form = NativeForm(interaction.user.id, title, "Confirm your own decision.", fields, vote)
        await reply(interaction, form.text(), form)
        return
    if step == "city_foundation":
        fields = [
            Field("name", "Name of the actual new city"),
            Field("cell", "Actual map square in x,y form"),
            Field("account", "Describe the new city", paragraph=True),
        ]

        async def establish(click: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.establish_city,
                viewer_from_interaction(click),
                str(click.id),
                case,
                data["revision"],
                values["name"],
                coordinates(values["cell"]),
                values["account"],
            )
            return "The city is on the map. Reopen the private Inbox for the next step."

        form = NativeForm(
            interaction.user.id, title, "Establish one actual city.", fields, establish
        )
        await reply(interaction, form.text(), form)
        return

    async def choose(click: discord.Interaction, site: str) -> None:
        npcs = tuple(data["locations"][site]["npcs"].items())
        fields = [
            Field("name", "Name of the Gorgon in the ruins"),
            Field(
                "kind",
                "Gorgon Class",
                (
                    ("benevolent", "Benevolent · 2 Assets"),
                    ("dormant", "Dormant · 3 Assets"),
                    ("erratic", "Erratic · 4 Assets"),
                ),
            ),
            Field("type", "Gorgon Type", TYPES),
            Field("assets", "Asset names, one per line", paragraph=True),
            Field("weakness", "Core weakness, protected by the first Asset", paragraph=True),
            Field("account", "Record the actual destruction", paragraph=True),
        ]
        if npcs:
            fields.append(
                Field(
                    "occupants",
                    "Every NPC actually inside",
                    npcs,
                    0,
                    min(len(npcs), 25),
                    required=False,
                )
            )

        async def ruin(confirm: discord.Interaction, values: dict[str, Any]) -> str:
            arrival = Arrival(
                kind=values["kind"][0],
                name=values["name"],
                type=values["type"][0],
                assets=tuple(x.strip() for x in values["assets"].splitlines() if x.strip()),
                weakness=values["weakness"],
            )
            await asyncio.to_thread(
                service.ruin,
                viewer_from_interaction(confirm),
                str(confirm.id),
                case,
                data["revision"],
                site,
                arrival,
                tuple(values.get("occupants", ())),
                values["account"],
            )
            return "The ruin and Gorgon are recorded. Reopen the private Inbox to continue."

        form = NativeForm(
            click.user.id,
            title,
            "Record the destruction, any actual occupants of the base, and the arriving Gorgon.",
            fields,
            ruin,
        )
        await reply(click, form.text(), form)

    options = tuple((key, value["label"]) for key, value in data["locations"].items())
    if not options:
        await reply(interaction, "The original Timeskip awaits an eligible location.")
        return
    await Picker(
        interaction.user.id, "Choose the actual location that fell.", options, choose
    ).show(interaction)
