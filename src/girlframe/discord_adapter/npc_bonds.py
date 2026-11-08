"""Private NPC Bond draft selectors; persistence uses the existing creation save."""

from typing import Any

import discord

from girlframe.discord_adapter.creation import CreationView, clean
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.npc_bonds import NPC_ROLES


class NpcSelect(discord.ui.Select["NpcView"]):
    def __init__(self, parent: "NpcView"):
        self.parent_view = parent
        selected = {x.slot for x in parent.parent.draft.npc_bonds}
        super().__init__(
            placeholder="Choose NPC roles (Oldgen: two; others: one or two)",
            min_values=0,
            max_values=2,
            options=[
                discord.SelectOption(label=label, value=str(i), default=i in selected)
                for i, label in enumerate(NPC_ROLES[parent.parent.draft.girl_playbook])
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        parent = self.parent_view.parent
        previous = {x.slot: x.model_dump(mode="json") for x in parent.draft.npc_bonds}
        try:
            values: dict[str, Any] = {
                "npc_bonds": [previous.get(int(i), {"slot": int(i)}) for i in self.values]
            }
            if parent.draft.girl_details is not None:
                details = parent.draft.girl_details.model_dump(mode="json")
                details["investors"] = [
                    x for x in details["investors"] if str(x["npc_slot"]) in self.values
                ]
                values["girl_details"] = details
            parent.update(**values)
        except ValueError:
            await self.parent_view.render(interaction, "Choose distinct legal NPC roles.\n")
            return
        await self.parent_view.render(interaction)


class NpcModal(discord.ui.Modal):
    def __init__(self, parent: CreationView):
        super().__init__(title="Private NPC details")
        self.parent, self.generation = parent, parent.generation
        self.fields: list[discord.ui.TextInput[Any]] = []
        for bond in parent.draft.npc_bonds:
            role = NPC_ROLES[parent.draft.girl_playbook][bond.slot]
            for label, value, maximum in (
                (role + " — name", bond.name, 80),
                (role + " — feelings", bond.feelings, 500),
            ):
                field: discord.ui.TextInput[Any] = discord.ui.TextInput(
                    label=label[:45],
                    default=value,
                    required=False,
                    max_length=maximum,
                    style=discord.TextStyle.paragraph,
                )
                self.fields.append(field)
                self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.parent.interaction_check(interaction):
            return
        if self.generation != self.parent.generation:
            await self.parent.render(
                interaction, "Choices changed. Reopen NPC details; saved progress preserved.\n"
            )
            return
        self.parent.update(
            npc_bonds=[
                {
                    "slot": bond.slot,
                    "name": str(self.fields[2 * i]),
                    "feelings": str(self.fields[2 * i + 1]),
                }
                for i, bond in enumerate(self.parent.draft.npc_bonds)
            ]
        )
        await self.parent.render(interaction)

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item[Any] | None = None,
    ) -> None:
        await reply(
            interaction, "NPC form unavailable. Reopen /character build to resume saved progress."
        )


class NpcView(discord.ui.View):
    def __init__(self, parent: CreationView):
        super().__init__(timeout=600)
        self.parent = parent
        self.refresh()

    def refresh(self) -> None:
        for child in list(self.children):
            if isinstance(child, discord.ui.Select):
                self.remove_item(child)
        self.add_item(NpcSelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await self.parent.interaction_check(interaction)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]
    ) -> None:
        await reply(
            interaction, "NPC form unavailable. Reopen /character build to resume saved progress."
        )

    async def render(self, interaction: discord.Interaction, prefix: str = "") -> None:
        self.refresh()
        chosen = [
            clean(NPC_ROLES[self.parent.draft.girl_playbook][x.slot])
            + (": " + clean(x.name) if x.name else "")
            for x in self.parent.draft.npc_bonds
        ]
        text = (
            prefix
            + "**Private NPC Bond choices — unsaved edits**\n"
            + ("\n".join(chosen) or "No roles selected.")
        )
        text += (
            "\nOldgen chooses two; other Girls choose one or two. "
            "Names and written feelings are optional. Return and Save progress to persist."
        )
        await interaction.response.edit_message(
            content=text, view=self, allowed_mentions=discord.AllowedMentions.none()
        )

    @discord.ui.button(label="Optional names / feelings", row=1)
    async def details(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if not self.parent.draft.npc_bonds:
            await reply(interaction, "Select NPC roles first.", self)
            return
        await interaction.response.send_modal(NpcModal(self.parent))

    @discord.ui.button(label="Back to creation", row=2)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        await self.parent.render(interaction)
