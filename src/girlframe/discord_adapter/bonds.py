"""Private Bond proposal review and restart-safe recipient decisions."""

import asyncio
from typing import Any

import discord
from discord import app_commands

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.creation import clean
from girlframe.discord_adapter.onboarding import action_gate, reply
from girlframe.engine.bonds import PROMPTS, BondProposal, starting_kind, starting_role
from girlframe.services.bonds import BondService, Decision
from girlframe.services.onboarding import WorkflowError


class OwnerView(discord.ui.View):
    def __init__(self, service: BondService, owner: int):
        super().__init__(timeout=600)
        self.service, self.owner = service, owner

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "This form belongs to another player.")
            return False
        try:
            await asyncio.to_thread(self.service.authorize, viewer_from_interaction(interaction))
            return True
        except WorkflowError as error:
            await reply(interaction, str(error))
            return False

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]
    ) -> None:
        await reply(
            interaction, "Bond form unavailable. Reopen /character bonds to check saved progress."
        )


def proposal_text(row: dict[str, Any]) -> str:
    girl = row["girl_playbook"]
    return (
        f"**Starting Bond setup — {starting_kind(girl)} / {starting_role(girl)}**\n"
        f"From player {row['source_id']} to player {row['target_id']}\n"
        f"Prompt: {clean(PROMPTS[girl][row['prompt']])}\n"
        f"Shared context: {clean(row['context']) or '(none)'}\n"
        + ("AM counterpart: this Girl is Jailbroken.\n" if girl == "AM" else "")
        + "This is a draft setup agreement. It applies no game effects or fictional actions."
    )


class PromptSelect(discord.ui.Select["ProposalView"]):
    def __init__(self, parent: "ProposalView"):
        self.parent_view = parent
        super().__init__(
            placeholder="Choose a starting playbook prompt",
            options=[
                discord.SelectOption(label=label, value=str(i))
                for i, label in enumerate(PROMPTS[parent.prepared["girl_playbook"]])
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.parent_view.prompt = int(self.values[0])
        for option in self.options:
            option.default = option.value == self.values[0]
        await interaction.response.edit_message(
            content="Prompt selected. Review shared context, then confirm the proposal.",
            view=self.parent_view,
            allowed_mentions=discord.AllowedMentions.none(),
        )


class ContextModal(discord.ui.Modal):
    def __init__(self, parent: "ProposalView"):
        super().__init__(title="Shared Bond context")
        self.parent_view = parent
        self.prompt = parent.prompt
        self.context: discord.ui.TextInput[Any] = discord.ui.TextInput(
            label="Context visible to both players",
            max_length=500,
            required=False,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.context)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        parent = self.parent_view
        if not await parent.interaction_check(interaction):
            return
        if self.prompt is None:
            await reply(interaction, "Choose a starting prompt first.")
            return
        proposal = BondProposal(
            target_id=parent.target, prompt=self.prompt, context=str(self.context)
        )
        view = ConfirmProposal(parent.service, parent.owner, parent.prepared, proposal)
        row = parent.prepared | {
            "source_id": str(parent.owner),
            "target_id": str(parent.target),
            "prompt": self.prompt,
            "context": str(self.context),
        }
        await reply(interaction, proposal_text(row) + "\nConfirm to save a pending proposal.", view)

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item[Any] | None = None,
    ) -> None:
        await reply(interaction, "Could not review the proposal. Reopen /character bond.")


class ProposalView(OwnerView):
    def __init__(self, service: BondService, owner: int, target: int, prepared: dict[str, Any]):
        super().__init__(service, owner)
        self.target, self.prepared = target, prepared
        self.prompt: int | None = None
        self.add_item(PromptSelect(self))

    @discord.ui.button(label="Review shared context", row=1)
    async def review(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if self.prompt is None:
            await reply(interaction, "Choose a starting prompt first.", self)
            return
        await interaction.response.send_modal(ContextModal(self))


class ConfirmProposal(OwnerView):
    def __init__(
        self, service: BondService, owner: int, prepared: dict[str, Any], proposal: BondProposal
    ):
        super().__init__(service, owner)
        self.prepared, self.proposal = prepared, proposal

    @discord.ui.button(label="Confirm proposal", style=discord.ButtonStyle.primary)
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
                self.service.propose,
                viewer_from_interaction(interaction),
                str(interaction.id),
                self.prepared["source_revision"],
                self.prepared["target_revision"],
                self.proposal,
            )
            await reply(
                interaction,
                "Proposal saved: "
                + result["id"]
                + ". Review it with /character bonds. No notification was sent.",
            )
        except WorkflowError as error:
            await reply(interaction, str(error))


class DecisionView(OwnerView):
    def __init__(self, service: BondService, owner: int, row: dict[str, Any]):
        super().__init__(service, owner)
        self.row = row
        recipient = str(owner) == row["target_id"]
        self.accept.disabled = not (recipient and row["state"] == "pending" and not row["stale"])
        self.decline.disabled = not (recipient and row["state"] == "pending")
        self.withdraw.disabled = not (
            row["state"] == "accepted" or (not recipient and row["state"] == "pending")
        )

    async def decide(self, interaction: discord.Interaction, decision: Decision) -> None:
        if not await self.interaction_check(interaction) or not await action_gate(
            interaction, "metadata"
        ):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            result = await asyncio.to_thread(
                self.service.decide,
                viewer_from_interaction(interaction),
                str(interaction.id),
                self.row["id"],
                self.row["revision"],
                decision,
            )
            await reply(
                interaction,
                "Setup proposal "
                + result["state"]
                + ". Reopen /character bonds for the saved record.",
            )
        except WorkflowError as error:
            await reply(interaction, str(error))

    @discord.ui.button(label="Accept setup", style=discord.ButtonStyle.primary)
    async def accept(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await self.decide(interaction, "accept")

    @discord.ui.button(label="Decline")
    async def decline(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await self.decide(interaction, "decline")

    @discord.ui.button(label="Withdraw", style=discord.ButtonStyle.danger)
    async def withdraw(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await self.decide(interaction, "withdraw")


class BondSelect(discord.ui.Select["BondListView"]):
    def __init__(self, parent: "BondListView", rows: list[dict[str, Any]]):
        self.parent_view = parent
        super().__init__(
            placeholder="Choose a saved proposal to review",
            options=[
                discord.SelectOption(
                    label=row["id"][:8]
                    + " / "
                    + row["state"]
                    + (" / stale" if row["stale"] else ""),
                    value=row["id"],
                    description="From " + row["source_id"] + " to " + row["target_id"],
                )
                for row in rows
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        row = await asyncio.to_thread(
            self.parent_view.service.get, viewer_from_interaction(interaction), self.values[0]
        )
        view = DecisionView(self.parent_view.service, self.parent_view.owner, row)
        await interaction.response.edit_message(
            content=proposal_text(row)
            + "\nSaved state: "
            + row["state"]
            + (" — STALE: profiles changed or membership inactive." if row["stale"] else ""),
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )


class BondListView(OwnerView):
    def __init__(self, service: BondService, owner: int, rows: list[dict[str, Any]]):
        super().__init__(service, owner)
        self.add_item(BondSelect(self, rows))


def register_bonds(tree: app_commands.CommandTree, guild_id: int, service: BondService) -> None:
    character = tree.get_command("character", guild=discord.Object(id=guild_id))
    assert isinstance(character, app_commands.Group)

    @character.command(name="bond", description="Propose a private starting Bond to another player")
    async def bond(interaction: discord.Interaction, member: discord.Member) -> None:
        if not await action_gate(interaction, "metadata"):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            prepared = await asyncio.to_thread(
                service.prepare, viewer_from_interaction(interaction), member.id
            )
            await reply(
                interaction,
                "Choose your starting prompt. After confirmation, "
                "shared context is visible to the other player.",
                ProposalView(service, interaction.user.id, member.id, prepared),
            )
        except WorkflowError as error:
            await reply(interaction, str(error))

    @character.command(
        name="bonds", description="Privately review and resume your saved Bond proposals"
    )
    async def bonds(interaction: discord.Interaction, before: str | None = None) -> None:
        if not await action_gate(interaction, "metadata"):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        rows = await asyncio.to_thread(service.list, viewer_from_interaction(interaction), before)
        if not rows:
            await reply(interaction, "No proposals on this page. Use /character bond to start one.")
            return
        text = "Your private setup proposals. Choose one to review; activation remains pending."
        if len(rows) == 20:
            text += "\nNext page: /character bonds before:" + rows[-1]["id"]
        await reply(interaction, text, BondListView(service, interaction.user.id, rows))
