"""Lossless private memory readback, independently of the native form's step controls."""

import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import discord

from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.onboarding import WorkflowError

LIMIT = 1000
Authorize = Callable[[discord.Interaction], Awaitable[None]]
Submit = Callable[[discord.Interaction, dict[str, Any]], Awaitable[str | None]]


def text_units(text: str) -> int:
    """Conservative Discord budget: astral code points occupy two UTF-16 units."""
    return sum(2 if ord(char) > 0xFFFF else 1 for char in text)


@dataclass(frozen=True)
class TextPage:
    content: str
    body: str


def paginate(text: str, heading: str) -> tuple[TextPage, ...]:
    """Split already escaped display text; never cut an escape or drop whitespace."""
    atoms: list[str] = []
    index = 0
    while index < len(text):
        end = index + 1
        if text[index] == "\\" and end < len(text):
            end += 1
        elif text[index] == "@" and text[end : end + 1] == "\u200b":
            end += 1
        token = text[index:end]
        joined = atoms and (
            token == "\u200d"
            or atoms[-1].endswith("\u200d")
            or unicodedata.category(token[0]).startswith("M")
            or 0x1F3FB <= ord(token[0]) <= 0x1F3FF
            or token == "\n"
            and atoms[-1] == "\r"
            or len(token) == len(atoms[-1]) == 1
            and 0x1F1E6 <= ord(token) <= 0x1F1FF
            and 0x1F1E6 <= ord(atoms[-1]) <= 0x1F1FF
        )
        if joined:
            atoms[-1] += token
        else:
            atoms.append(token)
        index = end
    expected = 1
    while True:
        budget = LIMIT - text_units(f"{heading} ({expected}/{expected})\n")
        if budget < 4:
            raise ValueError("The fixed memory heading leaves no safe content budget")
        chunks: list[str] = []
        start = 0
        while start < len(atoms):
            if text_units(atoms[start]) > budget:
                # A pathological combining run can exceed a whole page. Preserve
                # every code point rather than omit it or loop on an oversized unit.
                token = atoms[start]
                units: list[str] = []
                offset = 0
                while offset < len(token):
                    width = 2 if token[offset] == "\\" and offset + 1 < len(token) else 1
                    units.append(token[offset : offset + width])
                    offset += width
                atoms[start : start + 1] = units
            end, used, boundary = start, 0, start
            while end < len(atoms) and used + text_units(atoms[end]) <= budget:
                used += text_units(atoms[end])
                end += 1
                if atoms[end - 1][-1].isspace():
                    boundary = end
            if end < len(atoms) and boundary > start:
                end = boundary
            chunks.append("".join(atoms[start:end]))
            start = end
        chunks = chunks or [""]
        count = len(chunks)
        if count == expected:
            return tuple(
                TextPage(f"{heading} ({i}/{count})\n" + chunk, chunk)
                for i, chunk in enumerate(chunks, 1)
            )
        expected = count


async def allowed(interaction: discord.Interaction, owner: int, authorize: Authorize) -> bool:
    if interaction.user.id != owner:
        await reply(interaction, "This private memory view belongs to another reader.")
        return False
    try:
        await authorize(interaction)
    except WorkflowError:
        await reply(interaction, "This private memory is unavailable. Reopen your requests.")
        return False
    return True


async def acknowledge(interaction: discord.Interaction) -> None:
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)


class MemoryHistory(discord.ui.View):
    def __init__(self, owner: int, text: str, authorize: Authorize):
        super().__init__(timeout=600)
        self.owner, self.authorize = owner, authorize
        self.pages = paginate(text, "Memory History")
        self.index = 0
        self.controls()

    def controls(self) -> None:
        self.previous_page.disabled = self.index == 0
        self.next_page.disabled = self.index == len(self.pages) - 1

    def text(self) -> str:
        return self.pages[self.index].content

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.is_finished():
            await reply(interaction, "This view expired. Reopen the saved memory.")
            return False
        return await allowed(interaction, self.owner, self.authorize)

    async def on_timeout(self) -> None:
        self.stop()

    @discord.ui.button(label="Previous memory page")
    async def previous_page(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if not await self.interaction_check(interaction):
            return
        self.index = max(0, self.index - 1)
        self.controls()
        await acknowledge(interaction)
        await reply(interaction, self.text(), self)

    @discord.ui.button(label="Next memory page")
    async def next_page(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if not await self.interaction_check(interaction):
            return
        self.index = min(len(self.pages) - 1, self.index + 1)
        self.controls()
        await acknowledge(interaction)
        await reply(interaction, self.text(), self)


class MemoryForm(NativeForm):
    def __init__(
        self,
        owner: int,
        title: str,
        instructions: str,
        fields: list[Field],
        submit: Submit,
        *,
        authorize: Authorize,
    ):
        self.context_index = 0
        self.authorize_memory = authorize
        super().__init__(owner, title, instructions, fields, submit)

    def pages(self) -> tuple[TextPage, ...]:
        field = self.fields[self.index]
        lines = [self.instructions]
        for entry in self.fields:
            value = self.values.get(entry.key)
            if value is not None:
                labels = dict(entry.options)
                display = (
                    ", ".join(labels.get(x, x) for x in value) if entry.options else str(value)
                )
                lines.append(clean(entry.label) + ": " + clean(display))
        return paginate(
            "\n".join(lines),
            f"**{clean(self.title)}** · Step {self.index + 1}/{len(self.fields)}: "
            + clean(field.label)
            + " · Memory page",
        )

    def controls(self) -> None:
        super().controls()
        pages = self.pages()
        self.context_index = min(self.context_index, len(pages) - 1)
        self.earlier_context.disabled = self.context_index == 0
        self.later_context.disabled = self.context_index == len(pages) - 1

    def text(self) -> str:
        return self.pages()[self.context_index].content

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.is_finished():
            await reply(interaction, "This view expired. Reopen the saved memory.")
            return False
        return await super().interaction_check(interaction) and await allowed(
            interaction, self.owner, self.authorize_memory
        )

    async def on_timeout(self) -> None:
        self.stop()

    @discord.ui.button(label="Earlier memory page", row=4)
    async def earlier_context(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if not await self.interaction_check(interaction):
            return
        self.context_index = max(0, self.context_index - 1)
        await acknowledge(interaction)
        await self.present(interaction)

    @discord.ui.button(label="More memory", row=4)
    async def later_context(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if not await self.interaction_check(interaction):
            return
        self.context_index = min(len(self.pages()) - 1, self.context_index + 1)
        await acknowledge(interaction)
        await self.present(interaction)
