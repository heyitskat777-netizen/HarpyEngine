"""Owner-only Princess, Oldgen and NPC investor dropdowns; explicit builder save."""

from typing import Any

import discord

from girlframe.discord_adapter.creation import CreationView, clean
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.creation_details import DESIRES, MAXIMS, STANDARDS, GirlDetails
from girlframe.engine.npc_bonds import NPC_ROLES


class DetailSelect(discord.ui.Select["DetailsView"]):
    def __init__(self, parent: "DetailsView", kind: str):
        self.parent_view, self.kind = parent, kind
        details = parent.parent.draft.girl_details or GirlDetails()
        if kind == "npc":
            options = [
                discord.SelectOption(
                    label=NPC_ROLES["VATGROWN"][x.slot],
                    value=str(x.slot),
                    default=x.slot == parent.npc_slot,
                )
                for x in parent.parent.draft.npc_bonds
            ]
            maximum, minimum, row, placeholder = 1, 1, 0, "Choose your NPC investor"
        else:
            catalogue = STANDARDS if kind == "standard" else MAXIMS if kind == "maxims" else DESIRES
            selected = (
                (parent.standard_slot,)
                if kind == "standard"
                else details.maxims
                if kind == "maxims"
                else next(
                    (x.desires.slots for x in details.investors if x.npc_slot == parent.npc_slot),
                    (),
                )
            )
            options = [
                discord.SelectOption(label=label, value=str(i), default=i in selected)
                for i, label in enumerate(catalogue)
            ]
            maximum, minimum, row = (
                (1, 1, 0) if kind == "standard" else (2, 0, 0) if kind == "maxims" else (2, 0, 1)
            )
            placeholder = (
                "Choose your standard"
                if kind == "standard"
                else "Choose two maxims"
                if kind == "maxims"
                else "Choose one or two NPC desires"
            )
        super().__init__(
            options=options,
            min_values=minimum,
            max_values=maximum,
            row=row,
            placeholder=placeholder,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.parent_view
        selected = [int(x) for x in self.values]
        data = (view.parent.draft.girl_details or GirlDetails()).model_dump(mode="json")
        if self.kind == "npc":
            view.npc_slot = selected[0]
        elif self.kind == "standard":
            view.standard_slot = selected[0]
            old = data["own_standard"]
            data["own_standard"] = (
                {"slot": selected[0], "custom": ""}
                if selected[0] != 9
                else old
                if old and old["slot"] == 9
                else None
            )
            view.parent.update(girl_details=data)
        elif self.kind == "maxims":
            data["maxims"] = selected
            view.parent.update(girl_details=data)
        else:
            data["investors"] = [x for x in data["investors"] if x["npc_slot"] != view.npc_slot]
            if selected:
                data["investors"].append(
                    {"npc_slot": view.npc_slot, "desires": {"slots": selected}}
                )
            view.parent.update(girl_details=data)
        await view.render(interaction)


class OwnStandardModal(discord.ui.Modal):
    def __init__(self, parent: "DetailsView"):
        super().__init__(title="Your custom Princess standard")
        self.parent_view, self.generation = parent, parent.parent.generation
        own = (parent.parent.draft.girl_details or GirlDetails()).own_standard
        self.text: discord.ui.TextInput[Any] = discord.ui.TextInput(
            label="Standard", max_length=160, default=own.custom if own else ""
        )
        self.add_item(self.text)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        view = self.parent_view
        if not await view.interaction_check(interaction):
            return
        if view.parent.generation != self.generation or view.standard_slot != 9:
            await reply(interaction, "Choices changed. Reopen your custom standard form.")
            return
        data = (view.parent.draft.girl_details or GirlDetails()).model_dump(mode="json")
        data["own_standard"] = {"slot": 9, "custom": str(self.text)}
        try:
            view.parent.update(girl_details=data)
        except ValueError:
            await reply(interaction, "Enter nonempty custom standard text.")
            return
        await view.render(interaction)

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item[Any] | None = None,
    ) -> None:
        await reply(interaction, "Standard form unavailable. Reopen /character build.")


class DetailsView(discord.ui.View):
    def __init__(self, parent: CreationView):
        super().__init__(timeout=600)
        self.parent = parent
        own = (parent.draft.girl_details or GirlDetails()).own_standard
        self.standard_slot = own.slot if own else None
        self.npc_slot = parent.draft.npc_bonds[0].slot if parent.draft.npc_bonds else None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await self.parent.interaction_check(interaction)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]
    ) -> None:
        await reply(interaction, "Girl setup unavailable. Reopen /character build.")

    async def render(self, interaction: discord.Interaction) -> None:
        for child in list(self.children):
            if isinstance(child, discord.ui.Select):
                self.remove_item(child)
        girl = self.parent.draft.girl_playbook
        details = self.parent.draft.girl_details or GirlDetails()
        self.custom.disabled = girl != "PRINCESS" or self.standard_slot != 9
        if girl == "PRINCESS":
            self.add_item(DetailSelect(self, "standard"))
            text = "Your own standard: " + (
                clean(details.own_standard.label) if details.own_standard else "not chosen"
            )
            text += (
                "\nYour bonded Girl and Handler choose their standards through their inbox tasks."
            )
        elif girl == "OLDGEN":
            self.add_item(DetailSelect(self, "maxims"))
            text = "Maxims: " + (
                ", ".join(clean(MAXIMS[x]) for x in details.maxims) or "choose two"
            )
        elif girl == "VATGROWN":
            text = "Choose one or two desires for each selected starting NPC investor."
            if self.parent.draft.npc_bonds:
                self.add_item(DetailSelect(self, "npc"))
                self.add_item(DetailSelect(self, "desires"))
            else:
                text += " Select NPC Bonds in the builder first."
            for x in details.investors:
                text += (
                    "\n" + clean(NPC_ROLES["VATGROWN"][x.npc_slot]) + ": " + clean(x.desires.label)
                )
            text += "\nThe Handler chooses their own desires through their inbox task."
        else:
            text = "This Girl has no choices in this panel."
        edit = (
            interaction.edit_original_response
            if interaction.response.is_done()
            else interaction.response.edit_message
        )
        text += "\nShort labels refer to book PDF 32 (standards), 46 (maxims), 49 (investors)."
        await edit(
            content="**Girl setup — unsaved edits**\n"
            + text
            + "\nBack to creation, then Save progress to persist.",
            embed=None,
            view=self,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @discord.ui.button(label="Custom standard text", row=2)
    async def custom(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if self.parent.draft.girl_playbook == "PRINCESS" and self.standard_slot == 9:
            await interaction.response.send_modal(OwnStandardModal(self))

    @discord.ui.button(label="Back to creation", row=3)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        await self.parent.render(interaction)
