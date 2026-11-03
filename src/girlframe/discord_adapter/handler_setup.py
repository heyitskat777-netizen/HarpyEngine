"""Explicit administrator and Handler setup, with private review/confirmation."""

import asyncio
from collections.abc import Callable
from typing import Any

import discord
from discord import app_commands

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.onboarding import action_gate, reply
from girlframe.engine.handler_setup import PilotRef
from girlframe.services.handler_setup import HandlerService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class SetupView(discord.ui.View):
    def __init__(self, service: HandlerService, owner: int, admin: bool = False):
        super().__init__(timeout=600)
        self.service, self.owner, self.admin = service, owner, admin

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "This setup form belongs to another user.")
            return False
        try:
            await asyncio.to_thread(
                self.service.appointment_preview if self.admin else self.service.roster,
                viewer_from_interaction(interaction),
            )
            return True
        except WorkflowError as error:
            await reply(interaction, str(error))
            return False

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]
    ) -> None:
        await reply(interaction, "Setup unavailable. Reopen the command to check saved state.")


class ConfirmSetup(SetupView):
    def __init__(
        self,
        service: HandlerService,
        owner: int,
        operation: Callable[[GuildViewer, str], dict[str, Any]],
        admin: bool = False,
    ):
        super().__init__(service, owner, admin)
        self.operation = operation

    @discord.ui.button(label="Confirm setup change", style=discord.ButtonStyle.primary)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if not await self.interaction_check(interaction) or not await action_gate(
            interaction, "metadata"
        ):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            result = await asyncio.to_thread(
                self.operation, viewer_from_interaction(interaction), str(interaction.id)
            )
            await reply(
                interaction,
                f"Setup saved at revision {result['revision']}. Reopen /campaign setup to review.",
            )
        except WorkflowError as error:
            await reply(interaction, str(error))


class PilotSelect(discord.ui.Select["RankView"]):
    def __init__(self, parent: "RankView"):
        self.parent_view = parent
        super().__init__(
            placeholder="Choose the next Pilot, highest to lowest",
            options=[
                discord.SelectOption(
                    label=data["callsign"][:32], value=str(user), description="Player " + str(user)
                )
                for user, data in parent.prepared["pilots"].items()
                if user not in parent.order
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        parent = self.parent_view
        user = int(self.values[0])
        if user not in parent.prepared["pilots"] or user in parent.order:
            await reply(interaction, "Choose an unranked Pilot from this roster.", parent)
            return
        parent.order.append(user)
        parent.reviewed = False
        await parent.render(interaction)


class RankView(SetupView):
    def __init__(self, service: HandlerService, owner: int, prepared: dict[str, Any]):
        super().__init__(service, owner)
        self.prepared, self.reviewed = prepared, False
        self.order: list[int] = []
        self.refresh()

    def refresh(self) -> None:
        for item in list(self.children):
            if isinstance(item, discord.ui.Select):
                self.remove_item(item)
        if len(self.order) < len(self.prepared["pilots"]):
            self.add_item(PilotSelect(self))
        self.confirm.disabled = not self.reviewed

    async def render(self, interaction: discord.Interaction, prefix: str = "") -> None:
        self.refresh()
        lines = [
            f"{i + 1}. Player {user}"
            + (
                " — Ace"
                if i == 0
                else " — Dog"
                if i == len(self.order) - 1 and len(self.order) == len(self.prepared["pilots"])
                else " — Wings"
            )
            for i, user in enumerate(self.order)
        ]
        text = (
            prefix
            + "**Starting Status — unsaved highest to lowest**\n"
            + ("\n".join(lines) or "Choose every Pilot in order.")
        )
        text += (
            "\nPrincess must lead. Handler is outside this order. "
            "Review the complete order, then confirm. No mission effects run."
        )
        await interaction.response.edit_message(
            content=text, view=self, allowed_mentions=discord.AllowedMentions.none()
        )

    @discord.ui.button(label="Undo last", row=1)
    async def undo(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if self.order:
            self.order.pop()
        self.reviewed = False
        await self.render(interaction)

    @discord.ui.button(label="Review complete order", row=1)
    async def review(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        self.reviewed = len(self.order) == len(self.prepared["pilots"])
        await self.render(
            interaction,
            "Review all positions before confirming.\n"
            if self.reviewed
            else "Choose every Pilot first.\n",
        )

    @discord.ui.button(label="Confirm Status", style=discord.ButtonStyle.primary, row=2)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if (
            not await self.interaction_check(interaction)
            or not self.reviewed
            or not await action_gate(interaction, "metadata")
        ):
            return
        submitted = tuple(self.order)
        await interaction.response.defer(ephemeral=True, thinking=True)
        order = tuple(
            PilotRef(user_id=user, character_revision=self.prepared["pilots"][user]["revision"])
            for user in submitted
        )
        try:
            result = await asyncio.to_thread(
                self.service.rank,
                viewer_from_interaction(interaction),
                str(interaction.id),
                self.prepared["revision"],
                order,
            )
            await reply(
                interaction,
                f"Starting Status saved at revision {result['revision']}. "
                "/campaign setup shows the saved order.",
            )
        except WorkflowError as error:
            await reply(interaction, str(error), self)


def register_handler_setup(
    tree: app_commands.CommandTree, guild_id: int, service: HandlerService
) -> None:
    campaign = tree.get_command("campaign", guild=discord.Object(id=guild_id))
    assert isinstance(campaign, app_commands.Group)

    @campaign.command(
        name="handler",
        description="Administrator: review Handler appointment; omit member to revoke",
    )
    async def handler(
        interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        if not await action_gate(interaction, "metadata"):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            prepared = await asyncio.to_thread(
                service.appointment_preview, viewer_from_interaction(interaction)
            )
            target = member.id if member else None
            text = (
                f"Appoint Handler: {target if target else 'none (revoke)'}. "
                f"Previous: {prepared['handler_id']}. "
            )
            text += (
                "Confirming clears current Mentor nominations and Status setup; "
                "history is retained. No private-sheet access is granted."
            )
            await reply(
                interaction,
                text,
                ConfirmSetup(
                    service,
                    interaction.user.id,
                    lambda actor, key: service.appoint(actor, key, prepared["revision"], target),
                    admin=True,
                ),
            )
        except WorkflowError as error:
            await reply(interaction, str(error))

    @campaign.command(name="mentor", description="Handler: review a Newgirl Mentor nomination")
    async def mentor(
        interaction: discord.Interaction, newgirl: discord.Member, member: discord.Member
    ) -> None:
        if not await action_gate(interaction, "metadata"):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            prepared = await asyncio.to_thread(service.roster, viewer_from_interaction(interaction))
            if newgirl.id not in prepared["pilots"] or member.id not in prepared["pilots"]:
                raise WorkflowError("Choose two active Pilots with saved profiles.")
            first = PilotRef(
                user_id=newgirl.id, character_revision=prepared["pilots"][newgirl.id]["revision"]
            )
            second = PilotRef(
                user_id=member.id, character_revision=prepared["pilots"][member.id]["revision"]
            )
            text = f"Nominate player {member.id} as Mentor for Newgirl {newgirl.id}. "
            text += (
                "Newgirl then uses /character bond with this Mentor; both players review setup. "
                "Prior nomination consent becomes stale. Callsign choice remains pending."
            )
            await reply(
                interaction,
                text,
                ConfirmSetup(
                    service,
                    interaction.user.id,
                    lambda actor, key: service.mentor(
                        actor, key, prepared["revision"], first, second
                    ),
                ),
            )
        except WorkflowError as error:
            await reply(interaction, str(error))

    @campaign.command(
        name="status_setup",
        description="Handler: select and review the complete starting Status order",
    )
    async def status_setup(interaction: discord.Interaction) -> None:
        if not await action_gate(interaction, "metadata"):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            prepared = await asyncio.to_thread(service.roster, viewer_from_interaction(interaction))
            if not 2 <= len(prepared["pilots"]) <= 25:
                raise WorkflowError("UNSUPPORTED_RULE: this selector supports 2–25 active Pilots.")
            await reply(
                interaction,
                "Select all Pilots highest to lowest, review, then confirm.",
                RankView(service, interaction.user.id, prepared),
            )
        except WorkflowError as error:
            await reply(interaction, str(error))

    @campaign.command(
        name="setup", description="View saved Handler, starting Status and your Mentor setup"
    )
    async def setup(interaction: discord.Interaction) -> None:
        if not await action_gate(interaction, "metadata"):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            result = await asyncio.to_thread(service.view, viewer_from_interaction(interaction))
            lines = [
                f"Handler: {result['handler_id']}; active: {result['handler_active']}. "
                f"Setup revision {result['revision']}."
            ]
            order = result["status_order"]
            for i, pilot in enumerate(order):
                role = "Ace" if i == 0 else "Dog" if i == len(order) - 1 else "Wings"
                lines.append(f"{i + 1}. Player {pilot['user_id']} — {role}")
            lines.append(
                "Status needs review." if result["status_stale"] else "Status roster current."
            )
            for assignment in result["mentors"]:
                lines.append(
                    f"Newgirl {assignment['newgirl']['user_id']}: "
                    f"Mentor {assignment['mentor']['user_id']}; stale: {assignment['stale']}."
                )
            lines.append("Draft setup only; playable activation and remaining rules are pending.")
            await reply(interaction, "\n".join(lines)[:1950])
        except WorkflowError as error:
            await reply(interaction, str(error))
