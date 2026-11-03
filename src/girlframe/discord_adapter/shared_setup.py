"""Private source review and recipient agreement for starting shared choices."""

import asyncio
import json
from typing import Any

import discord
from discord import app_commands

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.creation import clean
from girlframe.discord_adapter.onboarding import action_gate, reply
from girlframe.engine.shared_setup import AM_ROLES, CallsignChoice, CourtChoice, Kind
from girlframe.services.bonds import Decision
from girlframe.services.onboarding import WorkflowError
from girlframe.services.shared_setup import SharedSetupService


class PrivateView(discord.ui.View):
    def __init__(self, service: SharedSetupService, owner: int):
        super().__init__(timeout=600)
        self.service, self.owner = service, owner

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "This setup form belongs to another player.")
            return False
        try:
            await asyncio.to_thread(
                self.service.bonds.authorize, viewer_from_interaction(interaction)
            )
            return True
        except WorkflowError as error:
            await reply(interaction, str(error))
            return False

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]
    ) -> None:
        await reply(
            interaction, "Setup form unavailable. Reopen /character requests to check saved state."
        )


class RoleSelect(discord.ui.Select["ChoiceView"]):
    def __init__(self, parent: "ChoiceView"):
        self.parent_view = parent
        super().__init__(
            placeholder="Choose the AM assigned to the other Girl",
            options=[discord.SelectOption(label=x, value=x) for x in AM_ROLES],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.parent_view.choice = CourtChoice.model_validate({"role": self.values[0]})
        self.parent_view.generation += 1
        for option in self.options:
            option.default = option.value == self.values[0]
        await self.parent_view.render(interaction)


class CallsignModal(discord.ui.Modal):
    def __init__(self, parent: "ChoiceView"):
        super().__init__(title="Mentor-chosen callsign")
        self.parent, self.generation = parent, parent.generation
        self.callsign: discord.ui.TextInput[Any] = discord.ui.TextInput(
            label="Newgirl's callsign", max_length=32
        )
        self.add_item(self.callsign)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.parent.interaction_check(interaction):
            return
        if self.generation != self.parent.generation:
            await reply(
                interaction,
                "Choice changed while this form was open; reopen the name form.",
                self.parent,
            )
            return
        try:
            self.parent.choice = CallsignChoice(callsign=str(self.callsign))
        except ValueError:
            await reply(
                interaction,
                "Use a nonempty, single-line callsign of up to 32 characters.",
                self.parent,
            )
            return
        self.parent.generation += 1
        await self.parent.render(interaction)

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item[Any] | None = None,
    ) -> None:
        await reply(interaction, "Name form unavailable. Reopen /character mentor_callsign.")


class ChoiceView(PrivateView):
    def __init__(
        self,
        service: SharedSetupService,
        owner: int,
        target: int,
        kind: Kind,
        prepared: dict[str, Any],
    ):
        super().__init__(service, owner)
        self.target, self.kind, self.prepared = target, kind, prepared
        self.choice: CourtChoice | CallsignChoice | None = None
        self.generation = 0
        if kind == "court":
            self.remove_item(self.name)
            self.add_item(RoleSelect(self))

    def text(self) -> str:
        value = (
            self.choice.role
            if isinstance(self.choice, CourtChoice)
            else self.choice.callsign
            if isinstance(self.choice, CallsignChoice)
            else "not selected"
        )
        detail = (
            "Four AMs stay with the pilot; the selected role goes to the recipient."
            if self.kind == "court"
            else "Accepted callsign is saved for activation; profile/nickname stays unchanged."
        )
        return (
            f"**Private {self.kind} setup request to player {self.target}**\n"
            + clean(value)
            + "\n"
            + detail
            + "\nConfirm, then recipient reviews with /character requests. Setup only."
        )

    async def render(self, interaction: discord.Interaction) -> None:
        if not interaction.response.is_done() and interaction.message is not None:
            await interaction.response.edit_message(
                content=self.text(), view=self, allowed_mentions=discord.AllowedMentions.none()
            )
        else:
            await reply(interaction, self.text(), self)

    @discord.ui.button(label="Enter callsign", row=1)
    async def name(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        await interaction.response.send_modal(CallsignModal(self))

    @discord.ui.button(label="Confirm request", style=discord.ButtonStyle.primary, row=2)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if not await self.interaction_check(interaction) or not await action_gate(
            interaction, "metadata"
        ):
            return
        choice = self.choice
        if choice is None:
            await reply(interaction, "Choose a role or enter the callsign first.", self)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            result = await asyncio.to_thread(
                self.service.propose,
                viewer_from_interaction(interaction),
                str(interaction.id),
                self.target,
                self.kind,
                self.prepared,
                choice,
            )
            await reply(
                interaction,
                "Request saved: "
                + result["id"]
                + ". Recipient uses /character requests. No notification was sent.",
            )
        except WorkflowError as error:
            await reply(interaction, str(error))


def request_text(row: dict[str, Any]) -> str:
    value = str(next(iter(json.loads(row["choice_json"]).values())))
    detail = (
        "Four AMs remain with the pilot; this role goes to the recipient."
        if row["kind"] == "court"
        else "Callsign applies at activation. Profile/nickname is unchanged."
    )
    return (
        f"**Private {row['kind']} setup**\n"
        f"From player {row['source_id']} to player {row['target_id']}\n"
        + clean(value)
        + "\nState: "
        + str(row["state"])
        + (" (STALE)" if row["stale"] else "")
        + "\n"
        + detail
        + "\nAccepting records draft setup only."
    )


class RequestView(PrivateView):
    def __init__(self, service: SharedSetupService, owner: int, row: dict[str, Any]):
        super().__init__(service, owner)
        self.row = row
        target = str(owner) == row["target_id"]
        self.accept.disabled = not (target and row["state"] == "pending" and not row["stale"])
        self.decline.disabled = not (target and row["state"] == "pending")
        self.withdraw.disabled = not (
            row["state"] == "accepted" or (not target and row["state"] == "pending")
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
                "Setup request "
                + result["state"]
                + ". Reopen /character build or /character requests to review saved choices.",
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


class RequestSelect(discord.ui.Select["RequestList"]):
    def __init__(self, parent: "RequestList", rows: list[dict[str, Any]]):
        self.parent_view = parent
        super().__init__(
            placeholder="Choose a saved setup request",
            options=[
                discord.SelectOption(
                    label=x["kind"] + " / " + x["state"] + " / " + x["id"][:8], value=x["id"]
                )
                for x in rows
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        parent = self.parent_view
        row = await asyncio.to_thread(
            parent.service.get, viewer_from_interaction(interaction), self.values[0]
        )
        await interaction.response.edit_message(
            content=request_text(row),
            view=RequestView(parent.service, parent.owner, row),
            allowed_mentions=discord.AllowedMentions.none(),
        )


class RequestList(PrivateView):
    def __init__(self, service: SharedSetupService, owner: int, rows: list[dict[str, Any]]):
        super().__init__(service, owner)
        self.add_item(RequestSelect(self, rows))


def register_shared_setup(
    tree: app_commands.CommandTree, guild_id: int, service: SharedSetupService
) -> None:
    character = tree.get_command("character", guild=discord.Object(id=guild_id))
    campaign = tree.get_command("campaign", guild=discord.Object(id=guild_id))
    assert isinstance(character, app_commands.Group) and isinstance(campaign, app_commands.Group)

    async def open_choice(
        interaction: discord.Interaction, member: discord.Member, kind: Kind
    ) -> None:
        if not await action_gate(interaction, "metadata"):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            prepared = await asyncio.to_thread(
                service.prepare, viewer_from_interaction(interaction), member.id, kind
            )
            view = ChoiceView(service, interaction.user.id, member.id, kind, prepared)
            await reply(interaction, view.text(), view)
        except WorkflowError as error:
            await reply(interaction, str(error))

    @character.command(
        name="court", description="Red Queen: propose one starting AM role for another Girl"
    )
    async def court(interaction: discord.Interaction, member: discord.Member) -> None:
        await open_choice(interaction, member, "court")

    @character.command(
        name="mentor_callsign", description="Mentor: propose your Newgirl's starting callsign"
    )
    async def mentor_callsign(interaction: discord.Interaction, member: discord.Member) -> None:
        await open_choice(interaction, member, "callsign")

    @character.command(
        name="requests", description="Open your guided private request and coordination inbox"
    )
    async def requests(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.inbox import InboxView
        from girlframe.services.inbox import InboxService

        if not await action_gate(interaction, "metadata"):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await InboxView(InboxService(service.store), interaction.user.id).present(interaction)
        except WorkflowError as error:
            await reply(interaction, str(error))

    @campaign.command(
        name="effective_status",
        description="Compare your effective setup Status to one other participant",
    )
    async def effective_status(interaction: discord.Interaction, member: discord.Member) -> None:
        if not await action_gate(interaction, "metadata"):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            result = await asyncio.to_thread(
                service.effective_status, viewer_from_interaction(interaction), member.id
            )
            answer = (
                "Unresolved" if result["higher"] is None else "Yes" if result["higher"] else "No"
            )
            await reply(
                interaction,
                f"You count as higher: {answer}. Basis: {result['basis']}. "
                "Setup comparison only; no orders or game effects run.",
            )
        except WorkflowError as error:
            await reply(interaction, str(error))
