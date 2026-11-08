"""Private native chooser for Princess standards and Handler investor desires."""

import asyncio
from typing import Any
from uuid import uuid4

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.creation import clean
from girlframe.discord_adapter.onboarding import action_gate, reply
from girlframe.engine.creation_details import DESIRES, STANDARDS, DesireChoice, Role, StandardChoice
from girlframe.services.creation_coordination import CoordinationService
from girlframe.services.onboarding import WorkflowError

ROLE_LABELS = {
    "princess_peer": "Princess standard — bonded Girl's choice",
    "princess_handler": "Princess standard — Handler's choice",
    "vatgrown_handler": "Vatgrown — Handler's investor desires",
}


class ChoiceSelect(discord.ui.Select["ChooserView"]):
    def __init__(self, parent: "ChooserView"):
        self.parent_view = parent
        desires = parent.role == "vatgrown_handler"
        super().__init__(
            placeholder="Choose one or two desires" if desires else "Choose a standard",
            min_values=1,
            max_values=2 if desires else 1,
            row=0,
            options=[
                discord.SelectOption(label=label, value=str(i), default=i in parent.slots)
                for i, label in enumerate(DESIRES if desires else STANDARDS)
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        parent = self.parent_view
        parent.slots = tuple(int(x) for x in self.values)
        parent.generation += 1
        await parent.render(interaction)


class CustomStandardModal(discord.ui.Modal):
    def __init__(self, parent: "ChooserView"):
        super().__init__(title="Custom Princess standard")
        self.parent_view, self.generation = parent, parent.generation
        self.text: discord.ui.TextInput[Any] = discord.ui.TextInput(
            label="Standard", max_length=160, default=parent.custom
        )
        self.add_item(self.text)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        parent = self.parent_view
        if not await parent.interaction_check(interaction):
            return
        if parent.generation != self.generation or parent.slots != (9,):
            await reply(interaction, "Choices changed. Reopen the custom standard form.")
            return
        parent.custom = str(self.text)
        parent.generation += 1
        await parent.render(interaction)

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item[Any] | None = None,
    ) -> None:
        await reply(interaction, "Custom standard unavailable. Reopen your inbox task.")


class ChooserView(discord.ui.View):
    def __init__(
        self,
        service: CoordinationService,
        actor: int,
        target: int,
        role: Role,
        context: dict[str, Any],
    ):
        super().__init__(timeout=600)
        self.service, self.actor, self.target, self.role, self.context = (
            service,
            actor,
            target,
            role,
            context,
        )
        self.slots: tuple[int, ...] = ()
        self.custom, self.generation = "", 0
        self.nonce = uuid4().hex[:12]

    def choice(self) -> StandardChoice | DesireChoice:
        try:
            return (
                DesireChoice(slots=self.slots)
                if self.role == "vatgrown_handler"
                else StandardChoice(
                    slot=self.slots[0], custom=self.custom if self.slots == (9,) else ""
                )
            )
        except (ValueError, IndexError):
            raise WorkflowError(
                "Choose the required options and enter custom text if selected."
            ) from None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.actor:
            await reply(interaction, "This choice belongs to another player.")
            return False
        try:
            context = await asyncio.to_thread(
                self.service.prepare, viewer_from_interaction(interaction), self.target, self.role
            )
            if context != self.context:
                raise WorkflowError("STALE_AUTHORITY: reopen this inbox task.")
            return True
        except WorkflowError as error:
            await reply(interaction, str(error))
            return False

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]
    ) -> None:
        await reply(interaction, "Playbook choice unavailable. Reopen /character requests.")

    async def render(self, interaction: discord.Interaction) -> None:
        self.send.custom_id = f"playbook-choice:{self.nonce}:{self.generation}"
        for child in list(self.children):
            if isinstance(child, discord.ui.Select):
                self.remove_item(child)
        self.add_item(ChoiceSelect(self))
        self.custom_text.disabled = self.role == "vatgrown_handler" or self.slots != (9,)
        try:
            choice = self.choice()
            label = choice.label
            self.send.disabled = False
        except WorkflowError:
            label = "Choose options below."
            self.send.disabled = True
        text = (
            "**"
            + ROLE_LABELS[self.role]
            + "**\nFor player "
            + str(self.target)
            + "\n"
            + clean(label)
        )
        text += "\nConfirm this private choice for the owner's review. No notification is sent."
        if self.role == "princess_handler":
            text += "\nThe Handler standard counts as an order when activated; no Play runs here."
        edit = (
            interaction.edit_original_response
            if interaction.response.is_done()
            else interaction.response.edit_message
        )
        await edit(
            content=text, embed=None, view=self, allowed_mentions=discord.AllowedMentions.none()
        )

    @discord.ui.button(label="Custom text", row=1)
    async def custom_text(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if self.role != "vatgrown_handler" and self.slots == (9,):
            await interaction.response.send_modal(CustomStandardModal(self))

    @discord.ui.button(
        label="Confirm and send for review", row=2, style=discord.ButtonStyle.primary
    )
    async def send(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        generation = self.generation
        try:
            choice = self.choice()
        except WorkflowError as error:
            await reply(interaction, str(error))
            return
        if (
            not isinstance(interaction.data, dict)
            or interaction.data.get("custom_id") != button.custom_id
        ):
            await reply(
                interaction, "This control belongs to an older choice. Review the current options."
            )
            return
        if not await self.interaction_check(interaction) or not await action_gate(
            interaction, "metadata"
        ):
            return
        if generation != self.generation:
            await reply(
                interaction, "Choices changed. Review the current selection before confirming."
            )
            return
        await interaction.response.defer()
        try:
            await asyncio.to_thread(
                self.service.propose,
                viewer_from_interaction(interaction),
                str(interaction.id),
                self.target,
                self.role,
                self.context,
                choice,
            )
            await interaction.edit_original_response(
                content="Saved for review in /character requests. No notification sent.",
                embed=None,
                view=None,
            )
            self.stop()
        except WorkflowError as error:
            await reply(interaction, str(error))
