"""Native zero/one mission declarations and explicit owner discussion attestation."""

from typing import Any

import discord

from girlframe.discord_adapter.creation import CreationView, clean
from girlframe.discord_adapter.onboarding import reply


class CounterpartSelect(discord.ui.Select["HistoryView"]):
    def __init__(self, parent: "HistoryView"):
        self.parent_view = parent
        super().__init__(
            row=0,
            placeholder="Choose a Cadre counterpart",
            options=[
                discord.SelectOption(
                    label=str(data["label"])[:100],
                    value=str(uid),
                    description="Player " + str(uid),
                    default=uid == parent.selected,
                )
                for uid, data in parent.cadre.items()
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.parent_view.selected = int(self.values[0])
        await self.parent_view.render(interaction)


class MissionSelect(discord.ui.Select["HistoryView"]):
    def __init__(self, parent: "HistoryView"):
        self.parent_view = parent
        chosen = parent.choices.get(parent.selected)
        super().__init__(
            row=1,
            placeholder="Choose your shared mission history",
            options=[
                discord.SelectOption(label=label, value=str(value), default=chosen == value)
                for value, label in (
                    (0, "We have never had a mission together"),
                    (1, "We have had one mission together"),
                )
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        parent = self.parent_view
        parent.choices[parent.selected] = int(self.values[0])
        parent.apply(False)
        await parent.render(interaction)


class HistoryView(discord.ui.View):
    def __init__(self, parent: CreationView, cadre: dict[int, dict[str, Any]]):
        super().__init__(timeout=600)
        self.parent, self.cadre = parent, cadre
        self.selected = next(iter(cadre), 0)
        self.choices: dict[int, int] = {
            x.user_id: x.missions
            for x in parent.draft.prior_missions
            if x.user_id in cadre and x.character_revision == cadre[x.user_id]["revision"]
        }
        if len(self.choices) != len(parent.draft.prior_missions) or set(self.choices) != set(cadre):
            self.apply(False)

    def apply(self, discussed: bool) -> None:
        self.parent.update(
            prior_missions=[
                {
                    "user_id": uid,
                    "character_revision": self.cadre[uid]["revision"],
                    "missions": value,
                }
                for uid, value in sorted(self.choices.items())
            ],
            cadre_discussed=discussed,
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await self.parent.interaction_check(interaction)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]
    ) -> None:
        await reply(interaction, "Mission-history form unavailable. Reopen /character build.")

    async def render(self, interaction: discord.Interaction, notice: str = "") -> None:
        for child in list(self.children):
            if isinstance(child, discord.ui.Select):
                self.remove_item(child)
        if self.cadre:
            self.add_item(CounterpartSelect(self))
            self.add_item(MissionSelect(self))
        self.discussed.disabled = not self.cadre or set(self.choices) != set(self.cadre)
        lines = ["**Newgirl: prior missions — unsaved edits**", notice]
        lines.append(f"Declared: {len(self.choices)}/{len(self.cadre)} counterparts.")
        if self.selected in self.cadre:
            value = self.choices.get(self.selected)
            lines.append(
                clean(str(self.cadre[self.selected]["label"]))
                + ": "
                + ("choose history" if value is None else str(value) + " shared missions")
            )
        lines.append("Discussed with the Cadre: " + str(self.parent.draft.cadre_discussed))
        lines.append(
            "Tell each counterpart in your conversation, then confirm below. "
            "This panel sends no message and assumes no agreement. Return and Save progress."
        )
        edit = (
            interaction.edit_original_response
            if interaction.response.is_done()
            else interaction.response.edit_message
        )
        await edit(
            content="\n".join(lines),
            embed=None,
            view=self,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @discord.ui.button(label="I discussed these with the Cadre", row=2)
    async def discussed(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if set(self.choices) != set(self.cadre) or not self.cadre:
            await self.render(interaction, "Choose history for every counterpart first.")
            return
        self.apply(True)
        await self.render(interaction)

    @discord.ui.button(label="Back to creation", row=3)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        await self.parent.render(interaction)
