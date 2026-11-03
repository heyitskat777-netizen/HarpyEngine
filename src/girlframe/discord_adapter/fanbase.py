"""Prince's private creation selectors; saving uses the parent creation service."""

from typing import Any

import discord

from girlframe.discord_adapter.creation import CreationView, DetailsModal, clean
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.fanbase import DEMOGRAPHICS, QUALITIES, Fanbase


class FanSelect(discord.ui.Select["FanbaseView"]):
    def __init__(self, parent: "FanbaseView", field: str, row: int):
        self.parent_view, self.field = parent, field
        base = parent.parent.draft.fanbase or Fanbase()
        demographic = field == "demographics"
        options = (
            (*DEMOGRAPHICS, "custom:1") if demographic else (*QUALITIES, "custom:1", "custom:2")
        )
        super().__init__(
            placeholder={
                "demographics": "Choose two fan demographics",
                "demanded": "Choose two demanded qualities",
                "rejected": "Choose two rejected qualities",
            }[field],
            row=row,
            min_values=0,
            max_values=2,
            options=[
                discord.SelectOption(
                    label=("Custom " + key[-1] + ": " if key.startswith("custom:") else "")
                    + base.label(key, demographic),
                    value=key,
                    default=key in getattr(base, field),
                )
                for key in options
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        parent = self.parent_view.parent
        base = (parent.draft.fanbase or Fanbase()).model_dump(mode="json")
        try:
            parent.update(fanbase=base | {self.field: self.values})
        except ValueError:
            await self.parent_view.render(
                interaction,
                "Choose distinct qualities; a quality cannot be both demanded and rejected.\n",
            )
            return
        await self.parent_view.render(interaction)


class FanbaseView(discord.ui.View):
    def __init__(self, parent: CreationView):
        super().__init__(timeout=600)
        self.parent = parent
        self.refresh()

    def refresh(self) -> None:
        for child in list(self.children):
            if isinstance(child, discord.ui.Select):
                self.remove_item(child)
        for row, field in enumerate(("demographics", "demanded", "rejected")):
            self.add_item(FanSelect(self, field, row))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await self.parent.interaction_check(interaction)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]
    ) -> None:
        await reply(interaction, "Could not update this form. Reopen /character build to resume.")

    async def render(self, interaction: discord.Interaction, prefix: str = "") -> None:
        self.refresh()
        base = self.parent.draft.fanbase or Fanbase()
        lines = ["**Prince fanbase — unsaved creation choices**"]
        for field, label in (
            ("demographics", "Demographics"),
            ("demanded", "Demands you be"),
            ("rejected", "Rejects you being"),
        ):
            lines.append(
                label
                + ": "
                + (
                    ", ".join(
                        clean(base.label(x, field == "demographics")) for x in getattr(base, field)
                    )
                    or "not selected"
                )
            )
        lines.append(
            "Choose two in each menu. Custom choices need text in Details. "
            "Then return and Save progress. No mechanics are applied here."
        )
        await interaction.response.edit_message(
            content=prefix + "\n".join(lines),
            view=self,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @discord.ui.button(label="Details / custom choices", row=3)
    async def details(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.send_modal(
            DetailsModal(self.parent, assets=False, playbook=True)
        )

    @discord.ui.button(label="Back to creation", row=4)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        await self.parent.render(interaction)
