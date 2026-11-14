"""Private actual-care review and original-player Girl Play exchange controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_medical import Care, Exchange
from girlframe.services.m3_medical import MedicalService


async def open_medical(
    interaction: discord.Interaction,
    service: MedicalService,
    identity: str,
    *,
    choosing: bool = False,
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if data["can_propose"]:
        prior = data["care"] or {}

        async def propose(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.propose,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                Care(account=values["account"], restore_vitals=values["vitals"][0] == "yes"),
            )
            return "Your actual care and waking proposal is saved for confirmation."

        form = NativeForm(
            interaction.user.id,
            "Actual medical care and waking",
            "Describe actual help and waking. The facilitator confirms those facts. "
            "The required Play exchange comes afterward.",
            [
                Field("account", "Describe actual care and waking", paragraph=True),
                Field(
                    "vitals",
                    "Does actual treatment restore inactive vital signs?",
                    (
                        ("no", "No additional vital-sign restoration"),
                        ("yes", "Explicitly restore vital signs"),
                    ),
                ),
            ],
            propose,
            values={
                "account": prior.get("account", ""),
                "vitals": ("yes" if prior.get("restore_vitals") else "no",),
            },
        )
        await reply(interaction, form.text(), form)
        return
    if data["can_confirm"]:
        text = (
            "**Actual care proposal**\n"
            + clean(data["care"]["account"])
            + "\nVital signs restored: "
            + str(data["care"]["restore_vitals"])
        )
        # The actual unescaped account is at most1200 characters; escaped pages are complete.
        if len(text) > 1300:
            await CarePages(service, identity, interaction.user.id).show(interaction)
            return
        await open_confirmation(interaction, service, identity, data, text)
        return
    if data.get("can_setup_standards") and not choosing:
        from girlframe.discord_adapter.m3_standards import open_standards
        from girlframe.services.m3_standards import StandardsService

        await open_standards(interaction, StandardsService(service.store), identity)
        return
    if data["can_exchange"]:
        choices = data.get("choices")
        if not choices or not choices["removed"] or not choices["acquired"]:
            await reply(
                interaction,
                "Your actual waking is recorded. No supported exchange is currently available. "
                "This required step remains pending.",
            )
            return

        async def exchange(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.exchange,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
                Exchange(removed=values["removed"][0], acquired=values["acquired"][0]),
            )
            return "Your Girl Play exchange is saved. Your original Girl and resources remain."

        form = NativeForm(
            interaction.user.id,
            "Your required Girl Play exchange",
            "Give up one available Girl Play and acquire one from an unused base Girl playbook. "
            "Some printed choices remain unavailable in this development build.",
            [
                Field(
                    "removed",
                    "Give up this Girl Play",
                    tuple((x["id"], x["name"]) for x in choices["removed"]),
                ),
                Field(
                    "acquired",
                    "Acquire this Girl Play",
                    tuple((x["id"], x["playbook"] + ": " + x["name"]) for x in choices["acquired"]),
                ),
            ],
            exchange,
        )
        await reply(interaction, form.text(), form)
        return
    await reply(
        interaction,
        "**Original medical recovery**\nStage: "
        + clean(data["stage"])
        + (
            "\nRecover the original character context before further effects."
            if data["stale"]
            else "\nWaiting for the original participant's actual decision."
            if data["stage"] != "complete"
            else "\nActual waking and the owned Play exchange are recorded. "
            "Open Requests to review the source-bound Handler rescue release."
        ),
    )


async def open_confirmation(
    interaction: discord.Interaction,
    service: MedicalService,
    identity: str,
    data: dict[str, Any],
    text: str,
) -> None:
    async def confirm(current: discord.Interaction, values: dict[str, Any]) -> str:
        accepted = values["decision"][0] == "yes"
        await asyncio.to_thread(
            service.confirm,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            data["game_revision"],
            accepted,
            values["evidence"],
        )
        return (
            "Actual waking is recorded. Its original player now chooses the required Play exchange."
            if accepted
            else "Proposal declined. No medical effects were applied."
        )

    form = NativeForm(
        interaction.user.id,
        "Confirm actual medical facts",
        text,
        [
            Field(
                "decision",
                "Your factual review",
                (
                    ("yes", "Confirm this actual care/waking"),
                    ("no", "Decline; these facts are not established"),
                ),
            ),
            Field("evidence", "Brief actual medical evidence", paragraph=True),
        ],
        confirm,
    )
    await reply(interaction, form.text(), form)


class CarePages(discord.ui.View):
    def __init__(self, service: MedicalService, identity: str, owner: int):
        super().__init__(timeout=600)
        self.service, self.identity, self.owner, self.index = service, identity, owner, 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "This actual-care review belongs to another participant.")
            return False
        return True

    async def show(self, interaction: discord.Interaction) -> None:
        data = await asyncio.to_thread(
            self.service.get, viewer_from_interaction(interaction), self.identity
        )
        text = clean((data["care"] or {}).get("account", ""))
        pages = [text[i : i + 1500] for i in range(0, max(1, len(text)), 1500)]
        self.index = min(max(self.index, 0), len(pages) - 1)
        self.previous.disabled, self.next.disabled = self.index == 0, self.index == len(pages) - 1
        self.review.disabled = self.index != len(pages) - 1 or not data["can_confirm"]
        await reply(
            interaction,
            "**Actual care proposal**\n"
            + pages[self.index]
            + f"\nPage {self.index + 1}/{len(pages)}.",
            self,
        )

    @discord.ui.button(label="Previous")
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        self.index -= 1
        await interaction.response.defer(ephemeral=True)
        await self.show(interaction)

    @discord.ui.button(label="Next")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        self.index += 1
        await interaction.response.defer(ephemeral=True)
        await self.show(interaction)

    @discord.ui.button(label="Review actual facts")
    async def review(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        data = await asyncio.to_thread(
            self.service.get, viewer_from_interaction(interaction), self.identity
        )
        await open_confirmation(
            interaction,
            self.service,
            self.identity,
            data,
            "Review the exact actual care shown on the preceding pages. Vital signs restored: "
            + str(data["care"]["restore_vitals"]),
        )
