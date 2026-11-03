"""Pair-only native Asset selection; no access to the owner's private draft."""

import asyncio
from typing import Any

import discord
from discord import app_commands

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.creation import clean
from girlframe.discord_adapter.onboarding import action_gate, reply
from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.pair_assets import PairNames
from girlframe.services.onboarding import WorkflowError
from girlframe.services.pair_assets import PairService


class PairSelect(discord.ui.Select["PairView"]):
    def __init__(self, parent: "PairView"):
        self.parent_view = parent
        super().__init__(
            placeholder="Choose two Girl Assets for your Bonded Pair",
            min_values=2,
            max_values=2,
            options=[
                discord.SelectOption(label=name, value=name, default=name in parent.names)
                for name in CATALOG["BONDED"]["assets"]
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            self.parent_view.names = PairNames(names=tuple(self.values)).names
        except ValueError:
            await reply(
                interaction, "Choose exactly two distinct Bonded Girl Assets.", self.parent_view
            )
            return
        for option in self.options:
            option.default = option.value in self.parent_view.names
        await interaction.response.edit_message(
            content=self.parent_view.text(),
            view=self.parent_view,
            allowed_mentions=discord.AllowedMentions.none(),
        )


class PairView(discord.ui.View):
    def __init__(self, service: PairService, owner: int, prepared: dict[str, Any]):
        super().__init__(timeout=600)
        self.service, self.owner, self.prepared = service, owner, prepared
        self.names: tuple[str, ...] = prepared["names"]
        self.add_item(PairSelect(self))

    def text(self) -> str:
        names = ", ".join(clean(x) for x in self.names) or "choose two below"
        return (
            f"**Pair-authored Girl Assets for player {self.prepared['owner_id']}**\n"
            + names
            + "\nReview your selection, then Confirm. The Bonded owner supplies descriptions. "
            "You cannot view or edit their private character details here."
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "This Pair form belongs to another player.")
            return False
        try:
            await asyncio.to_thread(
                self.service.prepare, viewer_from_interaction(interaction), self.prepared["bond_id"]
            )
            return True
        except WorkflowError as error:
            await reply(interaction, str(error))
            return False

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]
    ) -> None:
        await reply(
            interaction,
            "Pair form unavailable. Reopen /character pair_assets to check saved choices.",
        )

    @discord.ui.button(label="Confirm Pair Assets", style=discord.ButtonStyle.primary, row=1)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if not await self.interaction_check(interaction) or not await action_gate(
            interaction, "metadata"
        ):
            return
        try:
            names = PairNames(names=self.names)
        except ValueError:
            await reply(interaction, "Choose two Assets first.", self)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await asyncio.to_thread(
                self.service.choose,
                viewer_from_interaction(interaction),
                str(interaction.id),
                self.prepared["bond_id"],
                self.prepared["bond_revision"],
                self.prepared["revision"],
                names,
            )
            await reply(
                interaction,
                "Pair Assets saved: "
                + ", ".join(clean(x) for x in names.names)
                + ". Owner: reopen /character build, describe them and Save progress.",
            )
        except WorkflowError as error:
            await reply(interaction, str(error))


def register_pair_assets(
    tree: app_commands.CommandTree, guild_id: int, service: PairService
) -> None:
    character = tree.get_command("character", guild=discord.Object(id=guild_id))
    assert isinstance(character, app_commands.Group)

    @character.command(
        name="pair_assets",
        description="Accepted Pair: choose two starting Assets for a Bonded player",
    )
    async def pair_assets(interaction: discord.Interaction, member: discord.Member) -> None:
        if not await action_gate(interaction, "metadata"):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            prepared = await asyncio.to_thread(
                service.resolve, viewer_from_interaction(interaction), member.id
            )
            view = PairView(service, interaction.user.id, prepared)
            await reply(interaction, view.text(), view)
        except WorkflowError as error:
            await reply(interaction, str(error))
