"""Private native Timeskip approval and ordered world controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.m3_world import TYPES, coordinates
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.playbooks import FRAME_TYPES, GIRL_TYPES
from girlframe.services.m3_timeskip import (
    BASE_JOBS,
    DURATIONS,
    Arrival,
    RebelSuccessor,
    TimeskipService,
)


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
    if step in ("death", "death_ballot"):
        await _open_death(interaction, service, case, title, data)
        return
    if step == "base_contacts":
        await reply(interaction, "The Timeskip awaits the original players’ NPC contributions.")
        return
    if step == "rebel_succession":
        await _open_rebels(interaction, service, case, title, data)
        return
    if step == "identities":
        await reply(interaction, "The Timeskip awaits each original Girl’s two Identity changes.")
        return
    if step == "create_contact":
        await _open_contact(interaction, service, case, title, data)
        return
    if step in ("newgirl", "replacement") and not data["can_continue"]:
        message = (
            "The Timeskip awaits the original playbook setup or base aftermath."
            if step == "newgirl"
            else "The Timeskip awaits the original owner’s Newgirl activation."
        )
        await reply(interaction, message)
        return
    if step in ("newgirl", "choose_book", "replacement"):
        fields = [
            Field("confirm", "Proceed to the next printed step", (("continue", "Continue"),))
            if step != "choose_book"
            else Field(
                "book",
                "Your new playbook",
                tuple((k, v) for k, v in GIRL_TYPES.items() if k != "NEWGIRL"),
            )
        ]

        async def change(click: discord.Interaction, values: dict[str, Any]) -> str:
            actual = viewer_from_interaction(click)
            args = actual, str(click.id), case, data["revision"]
            if step != "choose_book":
                advance = (
                    service.advance_newgirl if step == "newgirl" else service.advance_replacement
                )
                await asyncio.to_thread(advance, *args)
                return "The Timeskip can proceed to the next printed step."
            await asyncio.to_thread(service.choose_book, *args, values["book"][0])
            return "Open your original playbook setup in the private Inbox."

        form = NativeForm(
            interaction.user.id,
            title,
            "Choose your new Girl playbook."
            if step == "choose_book"
            else "Confirm the original Newgirl setup.",
            fields,
            change,
        )
        await reply(interaction, form.text(), form)
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
    if step in ("city_foundation", "base_foundation"):
        site = "city" if step == "city_foundation" else "base"
        fields = [
            Field("name", "Name of the actual new " + site),
            Field("cell", "Actual map square in x,y form"),
            Field("account", "Describe the new " + site, paragraph=True),
        ]

        async def establish(click: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.establish_site,
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


async def _open_death(
    interaction: discord.Interaction,
    service: TimeskipService,
    identity: str,
    title: str,
    data: dict[str, Any],
) -> None:
    candidate = data.get("nominee")
    if data["step"] == "death" and "people" not in data:
        await reply(interaction, "The original table is considering its decision.")
        return
    if data["step"] == "death":
        options = tuple(data["people"].items())
        if not options:
            await reply(interaction, "The original table needs an eligible character.")
            return
        instruction = "Choose one character for consideration by the original table."
    else:
        options = (
            (("yes", "Agree"), ("no", "Return to the table"))
            if candidate
            else (("no", "Return the unavailable nomination to the table"),)
        )
        instruction = (
            "The proposed character is " + clean(candidate) + "."
            if candidate
            else ("The nominee is no longer available.")
        )

    async def confirm(click: discord.Interaction, values: dict[str, Any]) -> str:
        args = viewer_from_interaction(click), str(click.id), identity, data["revision"]
        if data["step"] == "death":
            await asyncio.to_thread(service.nominate, *args, values["choice"][0])
        else:
            await asyncio.to_thread(service.death_vote, *args, values["choice"][0] == "yes")
        return "Your recorded decision is saved."

    form = NativeForm(
        interaction.user.id,
        title,
        instruction,
        [Field("choice", "Your decision", options)],
        confirm,
    )
    await reply(interaction, form.text(), form)


async def _open_contact(
    interaction: discord.Interaction,
    service: TimeskipService,
    identity: str,
    title: str,
    data: dict[str, Any],
) -> None:
    async def confirm(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.introduce_contact,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            values["name"],
            values["job"][0],
            values["detail"],
            values["acquaintance"],
        )
        return "Your NPC is now at the new base."

    fields = [
        Field("name", "New NPC’s name"),
        Field("job", "Printed NPC job", tuple((x, x.replace("_", " ").title()) for x in BASE_JOBS)),
        Field("detail", "Describe the new NPC", paragraph=True),
        Field("acquaintance", "How your character knows them", paragraph=True),
    ]
    form = NativeForm(
        interaction.user.id,
        title,
        "Introduce your NPC at " + clean(data["site"]) + ".",
        fields,
        confirm,
    )
    await reply(interaction, form.text(), form)


async def _open_rebels(
    interaction: discord.Interaction,
    service: TimeskipService,
    identity: str,
    title: str,
    data: dict[str, Any],
) -> None:
    options = tuple(data["groups"].items())
    if not options:
        await reply(interaction, "Choose an actual existing Rebel group to establish its fall.")
        return

    async def confirm(click: discord.Interaction, values: dict[str, Any]) -> str:
        draft = RebelSuccessor(
            fallen=values["fallen"][0],
            name=values["name"],
            cell=coordinates(values["cell"]),
            handler=values["handler"],
            girl=values["girl"],
            frame=values["frame"][0],
            body_asset=values["body_asset"],
            frame_asset=values["frame_asset"],
            account=values["account"],
        )
        await asyncio.to_thread(
            service.replace_rebels,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            draft,
        )
        return "The original group has fallen. Its successor and their actual roles are recorded."

    fields = [
        Field("fallen", "Original Rebel group", options),
        Field("name", "Name of the new group"),
        Field("cell", "Actual refuge square in x,y form"),
        Field("handler", "Name of the actual Rebel Handler"),
        Field("girl", "Name of the actual Rebel Girl"),
        Field("frame", "The Rebel Girl’s actual Frame", tuple(FRAME_TYPES.items())),
        Field("body_asset", "One of the Rebel Girl’s actual body Assets"),
        Field("frame_asset", "One of the new Frame’s actual Assets"),
        Field("account", "Describe who fell and who rose", paragraph=True),
    ]
    form = NativeForm(
        interaction.user.id,
        title,
        "Establish the actual new group, Handler, and Girl.",
        fields,
        confirm,
    )
    await reply(interaction, form.text(), form)
