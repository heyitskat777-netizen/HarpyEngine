"""Owner-bound native selectors and narrative modals, reconstructable from saved choices."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import discord

from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.onboarding import WorkflowError


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    options: tuple[tuple[str, str], ...] = ()
    minimum: int = 1
    maximum: int = 1
    paragraph: bool = False
    required: bool = True


class FormSelect(discord.ui.Select["NativeForm"]):
    def __init__(self, parent: "NativeForm", field: Field):
        self.parent_form = parent
        self.field = field
        values = parent.values.get(field.key, ())
        options = field.options[parent.option_page * 25 : parent.option_page * 25 + 25]
        super().__init__(
            placeholder=field.label[:100],
            min_values=0 if field.maximum > 1 and len(field.options) > 25 else field.minimum,
            max_values=min(field.maximum, len(options)),
            row=0,
            options=[
                discord.SelectOption(label=label[:100], value=value, default=value in values)
                for value, label in options
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        selected = tuple(self.values)
        if self.field.maximum > 1 and len(self.field.options) > 25:
            window = {x.value for x in self.options}
            # Selections on another option page remain part of the same human choice.
            previous = tuple(
                x for x in self.parent_form.values.get(self.field.key, ()) if x not in window
            )
            selected = previous + selected
            if len(selected) > self.field.maximum:
                await reply(
                    interaction,
                    f"Choose at most {self.field.maximum} options across all pages.",
                    self.parent_form,
                )
                return
        self.parent_form.values[self.field.key] = selected
        await interaction.response.defer()
        await self.parent_form.present(interaction)


class NarrativeModal(discord.ui.Modal):
    def __init__(self, parent: "NativeForm", field: Field):
        super().__init__(title=field.label[:45], timeout=600)
        self.parent_form = parent
        self.field = field
        self.input: discord.ui.TextInput[discord.ui.Modal] = discord.ui.TextInput(
            label=field.label[:45],
            style=discord.TextStyle.paragraph if field.paragraph else discord.TextStyle.short,
            max_length=1200,
            required=field.required,
            default=str(parent.values.get(field.key, "")),
        )
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.parent_form.interaction_check(interaction):
            return
        self.parent_form.values[self.field.key] = str(self.input.value)
        await interaction.response.defer(ephemeral=True)
        await self.parent_form.present(interaction)


class NativeForm(discord.ui.View):
    def __init__(
        self,
        owner: int,
        title: str,
        instructions: str,
        fields: list[Field],
        submit: Callable[[discord.Interaction, dict[str, Any]], Awaitable[str | None]],
        *,
        values: dict[str, Any] | None = None,
    ):
        super().__init__(timeout=600)
        self.owner = owner
        self.title = title
        self.instructions = instructions
        self.fields = fields
        self.submit_action = submit
        self.values = values.copy() if values else {}
        self.index = 0
        self.option_page = 0
        self.completed = False
        self.controls()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "This form belongs to another player.")
            return False
        if self.completed:
            await reply(
                interaction, "This form was submitted. Reopen the saved action to continue."
            )
            return False
        return True

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]
    ) -> None:
        await reply(
            interaction, "This form is unavailable. Reopen the command to check saved progress."
        )

    def controls(self) -> None:
        for child in list(self.children):
            if isinstance(child, FormSelect):
                self.remove_item(child)
        field = self.fields[self.index]
        if field.options:
            self.add_item(FormSelect(self, field))
        self.edit.disabled = bool(field.options)
        self.previous.disabled = self.index == 0
        self.next.disabled = self.index == len(self.fields) - 1
        self.options_previous.disabled = self.option_page == 0
        self.options_next.disabled = (self.option_page + 1) * 25 >= len(field.options)

    def text(self) -> str:
        field = self.fields[self.index]
        lines = [
            f"**{clean(self.title)}**",
            self.instructions,
            f"\nStep {self.index + 1}/{len(self.fields)}: **{clean(field.label)}**",
        ]
        for entry in self.fields:
            value = self.values.get(entry.key)
            if value is None:
                continue
            if entry.options:
                labels = dict(entry.options)
                display = ", ".join(labels.get(x, x) for x in value) or "None"
            else:
                display = str(value)
            lines.append(clean(entry.label) + ": " + clean(display[:180]))
        return "\n".join(lines)[:1950]

    async def present(self, interaction: discord.Interaction) -> None:
        self.controls()
        await reply(interaction, self.text(), self)

    @discord.ui.button(label="Previous", row=1)
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        self.index = max(0, self.index - 1)
        self.option_page = 0
        await interaction.response.defer()
        await self.present(interaction)

    @discord.ui.button(label="Next", row=1)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        self.index = min(len(self.fields) - 1, self.index + 1)
        self.option_page = 0
        await interaction.response.defer()
        await self.present(interaction)

    @discord.ui.button(label="Enter details", row=1)
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        await interaction.response.send_modal(NarrativeModal(self, self.fields[self.index]))

    @discord.ui.button(label="Earlier options", row=2)
    async def options_previous(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        self.option_page = max(0, self.option_page - 1)
        await interaction.response.defer()
        await self.present(interaction)

    @discord.ui.button(label="More options", row=2)
    async def options_next(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        self.option_page += 1
        await interaction.response.defer()
        await self.present(interaction)

    @discord.ui.button(label="Review & Confirm", style=discord.ButtonStyle.success, row=3)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        missing = [
            x.label
            for x in self.fields
            if x.required and (x.key not in self.values or not self.values[x.key])
        ]
        if missing:
            await reply(interaction, "Complete: " + ", ".join(missing), self)
            return
        # This button is the explicit confirmation; selections alone never commit effects.
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            message = await self.submit_action(interaction, self.values)
        except WorkflowError as error:
            await reply(interaction, str(error), self)
            return
        except (ValueError, KeyError):
            await reply(interaction, "Choose valid values for every required step.", self)
            return
        self.completed = True
        self.stop()
        # A multi-step callback returns None after presenting its next screen.
        # Do not replace those controls with an empty/plain completion reply.
        if message is not None:
            await reply(interaction, message)


async def threaded(operation: Callable[[], Any]) -> Any:
    return await asyncio.to_thread(operation)
