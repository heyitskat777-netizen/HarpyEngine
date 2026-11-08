"""Private original sheets and explicit fresh-character creation after a career ends."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.drafts import DraftInput
from girlframe.engine.playbooks import FRAME_TYPES, GIRL_TYPES
from girlframe.services.m3_careers import CareerService
from girlframe.services.onboarding import WorkflowError


def pages(data: dict[str, Any]) -> list[str]:
    sheet, archive = data["sheet"], data["archive"]
    pieces = [
        "**Original sheet — " + clean(sheet["callsign"]) + "**",
        clean(sheet["girl"]) + " / " + clean(sheet["frame"]),
        "Career ended: " + archive["ending"].replace("_", " "),
        "Account: " + clean(archive["account"]),
        "Heat: " + str(sheet["heat"]) + " · Permissions: " + str(sheet["permissions"]),
        "**Identities**",
    ]
    pieces.extend(("☒ " if x["marked"] else "☐ ") + clean(x["name"]) for x in sheet["identities"])
    pieces.append("**Assets**")
    for asset in sheet["assets"]:
        pieces.append(
            clean(asset["family"].title() + ": " + asset["name"])
            + (" · damaged" if asset["damaged"] else " · undamaged")
            + (" · Void" if asset["void"] else "")
        )
        if asset["description"]:
            pieces.append(clean(asset["description"]))
    pieces.append("**Tags**")
    pieces.extend(("☒ " if x["marked"] else "☐ ") + clean(x["label"]) for x in sheet["tags"])
    result, current = [], ""
    for piece in pieces:
        for offset in range(0, len(piece), 1500):
            part = piece[offset : offset + 1500]
            if len(current) + len(part) + 1 > 1800:
                result.append(current)
                current = ""
            current += ("\n" if current else "") + part
    return result + ([current] if current else [])


class ArchiveView(discord.ui.View):
    def __init__(self, owner: int, service: CareerService, identity: str):
        super().__init__(timeout=600)
        self.owner, self.service, self.identity, self.page = owner, service, identity, 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "This original sheet belongs to its human owner.")
            return False
        return True

    async def show(self, interaction: discord.Interaction) -> None:
        data = await asyncio.to_thread(
            self.service.get, viewer_from_interaction(interaction), self.identity
        )
        content = pages(data)
        self.page = min(self.page, len(content) - 1)
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page + 1 == len(content)
        self.replacement.disabled = not data["can_replace"]
        await reply(
            interaction, content[self.page] + f"\nPage {self.page + 1}/{len(content)}.", self
        )

    @discord.ui.button(label="Previous", row=0)
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        self.page = max(0, self.page - 1)
        try:
            await self.show(interaction)
        except WorkflowError as error:
            await reply(interaction, str(error))

    @discord.ui.button(label="Next", row=0)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        await interaction.response.defer(ephemeral=True)
        self.page += 1
        try:
            await self.show(interaction)
        except WorkflowError as error:
            await reply(interaction, str(error))

    @discord.ui.button(label="Create a new character", row=1)
    async def replacement(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            await open_replacement(interaction, self.service, self.identity)
        except WorkflowError as error:
            await reply(interaction, str(error))


async def open_archive(
    interaction: discord.Interaction, service: CareerService, identity: str
) -> None:
    view = ArchiveView(interaction.user.id, service, identity)
    await view.show(interaction)


async def open_replacement(
    interaction: discord.Interaction, service: CareerService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if not data["can_replace"]:
        await reply(
            interaction,
            "A replacement draft already exists, or this is not the latest ended career. "
            "Continue your current character creation from /character build.",
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.begin_replacement,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["game_revision"],
            DraftInput(
                callsign=values["callsign"],
                girl_playbook=values["girl"][0],
                frame_playbook=values["frame"][0],
                notes=values.get("notes", ""),
            ),
        )
        return (
            "New draft saved. Complete the starting choices with /character build. "
            "Save a fresh review. The Handler must assign the new character's starting Status. "
            "Your original sheet and receipts remain archived."
        )

    form = NativeForm(
        viewer.user_id,
        "Create a new character",
        "This starts a distinct Girl. Old Heat, Permissions, Assets, Tags "
        "and relationships are not inherited.",
        [
            Field("callsign", "New callsign"),
            Field(
                "girl",
                "Girl playbook",
                (("VATGROWN", "VATGROWN"),)
                if data.get("vatgrown_death_required")
                else tuple((x, x) for x in GIRL_TYPES),
            ),
            Field("frame", "Frame playbook", tuple((x, x) for x in FRAME_TYPES)),
            Field("notes", "New private notes", paragraph=True, required=False),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_status(
    interaction: discord.Interaction, service: CareerService, owner: int, character: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    choices = await asyncio.to_thread(service.status_requests, viewer)
    data = next((x for x in choices if x["owner"] == owner and x["character"] == character), None)
    if data is None:
        raise WorkflowError("This original replacement Status request is unavailable.")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.assign_status,
            viewer_from_interaction(current),
            str(current.id),
            owner,
            character,
            data["game_revision"],
            int(values["position"][0]),
        )
        return "Starting Status recorded. The new character still requires explicit activation."

    options = tuple(
        (
            str(index),
            "Position "
            + str(index + 1)
            + (" — highest" if index == 0 else " — lowest" if index == data["maximum"] else ""),
        )
        for index in range(data["maximum"] + 1)
    )
    form = NativeForm(
        viewer.user_id,
        "New starting Status — " + clean(data["callsign"]),
        "Choose this new Girl's actual starting position. "
        "This does not restore the old Girl's Status.",
        [Field("position", "New starting Status", options)],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_return_offer(
    interaction: discord.Interaction, service: CareerService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    rows = await asyncio.to_thread(service.return_candidates, viewer)
    data = next((row for row in rows if row["id"] == identity), None)
    if data is None:
        raise WorkflowError("This original return needs its actual current Handler offer.")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.offer_return,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["game_revision"],
            int(values["position"][0]),
            values["account"],
        )
        return "Return offered. The original human owner must choose whether to resume."

    form = NativeForm(
        viewer.user_id,
        "Offer original return — " + clean(data["callsign"]),
        "Describe the actual release or return and choose its Status. The owner may decline.",
        [
            Field(
                "position",
                "Returning Status",
                tuple((str(i), "Position " + str(i + 1)) for i in range(data["maximum"] + 1)),
            ),
            Field("account", "Actual release or return", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_return(
    interaction: discord.Interaction, service: CareerService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get_return, viewer, identity)
    if not data["can_respond"]:
        raise WorkflowError("Only the original human owner may answer this return offer.")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.answer_return,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["game_revision"],
            accept=values["answer"][0] == "yes",
            account=values["account"],
        )
        return (
            "Original Girl resumed with her actual saved resources; confirm unknown positions "
            "before further physical Plays."
            if result["state"] == "returned"
            else "Return declined. Your active character and the original archive are preserved."
        )

    form = NativeForm(
        viewer.user_id,
        "Return — " + clean(data["callsign"]),
        clean(data["account"])
        + (
            "\nYour current Girl will be preserved in reserve if you accept."
            if data["current_callsign"]
            else ""
        ),
        [
            Field(
                "answer",
                "Choose your active character",
                (("no", "Decline this return"), ("yes", "Resume my original Girl")),
            ),
            Field("account", "Your choice", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
