"""Private owned Frantic Crisis choices backed by the actual Tag and Strain."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_frantic_crisis import CrisisService


async def open_crisis(
    interaction: discord.Interaction, service: CrisisService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if data["breakdown"]:
        await reply(interaction, "The actual Break Down roll is saved. Continue it in your Inbox.")
        return
    if data["location"]:
        await reply(interaction, "The selected site has fallen to ruin.")
        return
    if data["slot"]:
        await reply(interaction, "This Crisis already raised " + clean(data["track"]) + " to High.")
        return
    ruins = any(sites for _, sites in data["ruins"])
    if not data["available"] or not data["low"]:
        if data["immediate"] and interaction.channel_id is not None:
            await open_immediate(interaction, service, data, interaction.channel_id, ruins=ruins)
            return
        if ruins:
            await open_ruin(interaction, service, data)
            return
        await reply(
            interaction,
            "This Crisis remains pending. Reopen it from your joined scene.",
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.raise_track,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["slot"][0],
            values["track"][0],
        )
        return "The actual Low Strain track is now High."

    form = NativeForm(
        viewer.user_id,
        "Crisis Management",
        "You gained this Tag\n" + clean(data["tag"]),
        [
            Field(
                "slot",
                "Printed consequence",
                tuple(
                    (
                        x,
                        "Raise Low Strain to High. "
                        + ("First use" if x == "raise_first" else "Second use"),
                    )
                    for x in data["available"]
                ),
            ),
            Field("track", "Actual Low Strain", tuple((x, x.title()) for x in data["low"])),
        ],
        submit,
    )
    if data["immediate"] and interaction.channel_id is not None:
        form.add_item(ImmediateBreakdown(form, service, data, interaction.channel_id))
    if ruins:
        form.add_item(SiteRuin(form, service, data))
    await reply(interaction, form.text(), form)


class ImmediateBreakdown(discord.ui.Button[NativeForm]):
    def __init__(
        self, form: NativeForm, service: CrisisService, data: dict[str, Any], channel: int
    ):
        super().__init__(label="Break Down immediately", row=3)
        self.form, self.service, self.data, self.channel = form, service, data, channel

    async def callback(self, interaction: discord.Interaction) -> None:
        if await self.form.interaction_check(interaction):
            await open_immediate(interaction, self.service, self.data, self.channel)


async def open_immediate(
    interaction: discord.Interaction,
    service: CrisisService,
    data: dict[str, Any],
    channel: int,
    *,
    ruins: bool = False,
) -> None:
    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.break_now,
            viewer_from_interaction(current),
            str(current.id),
            data["id"],
            data["revision"],
            values["slot"][0],
            channel,
            values["account"],
        )
        return "The Break Down roll is saved. Continue its actual choices in your Inbox."

    form = NativeForm(
        interaction.user.id,
        "Break Down immediately",
        "You gained this Tag\n" + clean(data["tag"]),
        [
            Field(
                "slot",
                "Printed consequence",
                tuple(
                    (
                        x,
                        "Break Down immediately. "
                        + ("First use" if x == "break_first" else "Second use"),
                    )
                    for x in data["immediate"]
                ),
            ),
            Field("account", "What is happening in the original scene?", paragraph=True),
        ],
        submit,
    )
    if ruins:
        form.add_item(SiteRuin(form, service, data))
    await form.present(interaction)


class SiteRuin(discord.ui.Button[NativeForm]):
    def __init__(self, form: NativeForm, service: CrisisService, data: dict[str, Any]):
        super().__init__(label="A site falls to ruin", row=3)
        self.form, self.service, self.data = form, service, data

    async def callback(self, interaction: discord.Interaction) -> None:
        if await self.form.interaction_check(interaction):
            await open_ruin(interaction, self.service, self.data)


async def open_ruin(
    interaction: discord.Interaction, service: CrisisService, data: dict[str, Any]
) -> None:
    options = {
        str(i): (slot, site, label)
        for i, (slot, site, label) in enumerate(
            (slot, site, label) for slot, sites in data["ruins"] for site, label in sites
        )
    }
    labels = dict(city="City", base_first="Base 1", base_second="Base 2", base_third="Base 3")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        slot, site, _ = options[values["choice"][0]]
        await asyncio.to_thread(
            service.ruin,
            viewer_from_interaction(current),
            str(current.id),
            data["id"],
            data["revision"],
            slot,
            site,
            values["account"],
        )
        return "The selected site has fallen to ruin."

    await NativeForm(
        interaction.user.id,
        "A site falls to ruin",
        "You gained this Tag\n" + clean(data["tag"]),
        [
            Field(
                "choice",
                "Actual site and printed consequence",
                tuple(
                    (key, labels[slot] + " — " + clean(label))
                    for key, (slot, _, label) in options.items()
                ),
            ),
            Field("account", "Account of the actual destruction", paragraph=True),
        ],
        submit,
    ).present(interaction)
