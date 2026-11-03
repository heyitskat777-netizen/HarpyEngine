"""Private, resumable starting-choice wizard. Saves drafts, never activates rules."""

import asyncio
import json
from typing import Any

import discord
from discord import app_commands
from pydantic import ValidationError

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.onboarding import action_gate, reply
from girlframe.engine.creation import AssetChoice, CreationDraft, official_frame
from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.fanbase import Fanbase
from girlframe.engine.pair_assets import PairChoice
from girlframe.engine.shared_setup import AcceptedSetup
from girlframe.services.creation import CreationProgress, CreationService
from girlframe.services.onboarding import WorkflowError


def clean(value: str) -> str:
    return discord.utils.escape_markdown(discord.utils.escape_mentions(value))


def summary(
    draft: CreationDraft, pair: PairChoice | None = None, shared: tuple[AcceptedSetup, ...] = ()
) -> str:
    missing = draft.missing(pair.names if pair else ())
    return (
        "**Character creation — draft, not activated**\n"
        f"{clean(draft.girl_playbook)} / {clean(draft.frame_playbook)}\n"
        "Starting Identities: " + ", ".join(clean(x) for x in draft.identities) + "\n"
        "Girl Assets: "
        + (
            ", ".join(
                clean(x) for x in (pair.names if pair else tuple(a.name for a in draft.girl_assets))
            )
            or "not selected"
        )
        + "\n"
        "Frame Assets: "
        + (", ".join(clean(x.name) for x in draft.frame_assets) or "not selected")
        + "\n"
        + (
            "Extra Frame Asset: Enormous (does not use a normal slot).\n"
            if draft.intrinsic_frame_assets
            else ""
        )
        + (f"Void-altered Girl Asset: {clean(draft.void_asset)}\n" if draft.void_asset else "")
        + (
            "This step still needs: " + "; ".join(missing)
            if missing
            else "This starting-choice step is filled in."
        )
        + (
            "\nPrince fanbase Identities: "
            + ", ".join(clean(x) for x in draft.fanbase.additional_identities)
            if draft.fanbase
            else ""
        )
        + "".join(
            "\nAccepted "
            + ("Court role: " if x.kind == "court" else "Mentor callsign: ")
            + clean(x.value)
            for x in shared
        )
        + "\nBonds, Status, other playbook requirements and rules review remain before activation."
        "\nChoose/edit below, then **Save progress**. Reopen /character build to resume."
    )


def description_assets(view: "CreationView") -> tuple[AssetChoice, ...]:
    if view.draft.girl_playbook != "BONDED":
        return view.draft.girl_assets + view.draft.frame_assets
    descriptions = {x.name: x.description for x in view.draft.pair_asset_descriptions}
    names = view.progress.pair_choice.names if view.progress.pair_choice else ()
    return (
        tuple(AssetChoice(name=name, description=descriptions.get(name, "")) for name in names)
        + view.draft.frame_assets
    )


class AssetSelect(discord.ui.Select["CreationView"]):
    def __init__(self, parent: "CreationView", family: str, row: int):
        self.parent_view, self.family = parent, family
        draft = parent.draft
        key = draft.girl_playbook if family == "girl" else official_frame(draft.frame_playbook)
        selected = {x.name for x in getattr(draft, family + "_assets")}
        if family == "girl" and draft.girl_playbook == "BONDED" and parent.progress.pair_choice:
            selected = set(parent.progress.pair_choice.names)
        super().__init__(
            placeholder=f"Choose two {family.title()} Assets",
            min_values=0,
            max_values=2,
            row=row,
            disabled=key == "BONDED",
            options=[
                discord.SelectOption(label=name, value=name, default=name in selected)
                for name in CATALOG[key]["assets"]
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        previous = {
            a.name: a.description for a in getattr(self.parent_view.draft, self.family + "_assets")
        }
        values: dict[str, Any] = {
            self.family + "_assets": [
                {"name": name, "description": previous.get(name, "")} for name in self.values
            ]
        }
        if self.family == "girl" and self.parent_view.draft.void_asset not in self.values:
            values["void_asset"] = None
        try:
            self.parent_view.update(**values)
        except ValueError:
            await reply(interaction, "Select legal, distinct Assets for your playbook.")
            return
        await self.parent_view.render(interaction)


class VoidSelect(discord.ui.Select["CreationView"]):
    def __init__(self, parent: "CreationView"):
        self.parent_view = parent
        super().__init__(
            placeholder="Mockingbird: choose the Void-altered Girl Asset",
            row=2,
            options=[
                discord.SelectOption(
                    label=a.name, value=a.name, default=a.name == parent.draft.void_asset
                )
                for a in parent.draft.girl_assets
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            self.parent_view.update(void_asset=self.values[0])
        except (ValueError, IndexError):
            await reply(interaction, "Choose one of your selected Girl Assets.")
            return
        await self.parent_view.render(interaction)


class DetailsModal(discord.ui.Modal):
    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item[Any] | None = None,
    ) -> None:
        await reply(interaction, "Could not update this form. Reopen /character build to resume.")

    def __init__(self, parent: "CreationView", assets: bool, playbook: bool = False):
        super().__init__(
            title="Playbook details"
            if playbook
            else ("Describe selected Assets" if assets else "Character appearance")
        )
        self.parent_view, self.assets, self.generation = parent, assets, parent.generation
        self.playbook = playbook
        self.detail_keys: list[str] = []
        self.fields: list[discord.ui.TextInput[Any]] = []
        if playbook:
            items = []
            if parent.draft.girl_playbook == "VATGROWN":
                items.append(("Person who is your DNA basis", parent.draft.dna_basis, 300))
                self.detail_keys.append("dna_basis")
            if official_frame(parent.draft.frame_playbook) == "THE PRINCE":
                fanbase = parent.draft.fanbase or Fanbase()
                for key, label in (
                    ("custom_demographic", "Custom fan demographic"),
                    ("custom_quality_1", "Custom quality 1"),
                    ("custom_quality_2", "Custom quality 2"),
                ):
                    items.append((label, getattr(fanbase, key), 80))
                    self.detail_keys.append(key)
        elif assets:
            items = [(a.name[:45], a.description, 700) for a in description_assets(parent)]
        else:
            items = [
                ("Frame name", parent.draft.frame_name, 80),
                ("Girl appearance", parent.draft.girl_appearance, 700),
                ("Frame appearance", parent.draft.frame_appearance, 700),
            ]
        for label, value, maximum in items:
            field: discord.ui.TextInput[Any] = discord.ui.TextInput(
                label=label,
                default=value,
                max_length=maximum,
                required=False,
                style=discord.TextStyle.paragraph,
            )
            self.fields.append(field)
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.parent_view.interaction_check(interaction):
            return
        if self.parent_view.generation != self.generation:
            await reply(
                interaction, "Choices changed while this form was open. Reopen the details form."
            )
            return
        if self.playbook:
            details = dict(zip(self.detail_keys, (str(x) for x in self.fields), strict=True))
            update: dict[str, Any] = {}
            if "dna_basis" in details:
                update["dna_basis"] = details.pop("dna_basis")
            if details:
                update["fanbase"] = (self.parent_view.draft.fanbase or Fanbase()).model_dump(
                    mode="json"
                ) | details
            try:
                self.parent_view.update(**update)
            except ValueError:
                await reply(
                    interaction, "Use distinct custom labels that differ from the printed options."
                )
                return
        elif self.assets:
            draft = self.parent_view.draft
            values = [
                {"name": asset.name, "description": str(field)}
                for asset, field in zip(
                    description_assets(self.parent_view), self.fields, strict=True
                )
            ]
            split = len(description_assets(self.parent_view)) - len(draft.frame_assets)
            girl_key = (
                "pair_asset_descriptions" if draft.girl_playbook == "BONDED" else "girl_assets"
            )
            self.parent_view.update(**{girl_key: values[:split], "frame_assets": values[split:]})
        else:
            self.parent_view.update(
                frame_name=str(self.fields[0]),
                girl_appearance=str(self.fields[1]),
                frame_appearance=str(self.fields[2]),
            )
        await self.parent_view.render(interaction)


class CreationView(discord.ui.View):
    def __init__(self, service: CreationService, owner: int, progress: CreationProgress):
        super().__init__(timeout=600)
        self.service, self.owner, self.progress = service, owner, progress
        self.draft, self.generation = progress.draft, 0
        self.refresh_selects()
        self.playbook.disabled = not (
            self.draft.girl_playbook == "VATGROWN"
            or official_frame(self.draft.frame_playbook) == "THE PRINCE"
        )

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]
    ) -> None:
        await reply(interaction, "Could not update this form. Reopen /character build to resume.")

    def refresh_selects(self) -> None:
        for item in list(self.children):
            if isinstance(item, discord.ui.Select):
                self.remove_item(item)
        self.add_item(AssetSelect(self, "girl", 0))
        self.add_item(AssetSelect(self, "frame", 1))
        if self.draft.girl_playbook == "MOCKINGBIRD" and self.draft.girl_assets:
            self.add_item(VoidSelect(self))

    def update(self, **values: Any) -> None:
        self.draft = CreationDraft.model_validate_json(
            json.dumps(self.draft.model_dump(mode="json") | values)
        )
        self.generation += 1
        self.refresh_selects()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        try:
            if interaction.user.id != self.owner:
                raise WorkflowError("This creation form belongs to another player.")
            await asyncio.to_thread(self.service.get, viewer_from_interaction(interaction))
            return True
        except WorkflowError as error:
            await reply(interaction, str(error))
            return False

    async def render(self, interaction: discord.Interaction, prefix: str = "") -> None:
        if not interaction.response.is_done() and interaction.message is not None:
            await interaction.response.edit_message(
                content=prefix
                + summary(self.draft, self.progress.pair_choice, self.progress.shared_choices),
                view=self,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        await reply(
            interaction,
            prefix + summary(self.draft, self.progress.pair_choice, self.progress.shared_choices),
            self,
        )

    @discord.ui.button(label="Appearance", row=3)
    async def appearance(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.send_modal(DetailsModal(self, assets=False))

    @discord.ui.button(label="Asset descriptions", row=3)
    async def descriptions(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if not description_assets(self):
            await reply(interaction, "Select Assets first, then describe them.")
            return
        await interaction.response.send_modal(DetailsModal(self, assets=True))

    @discord.ui.button(label="Playbook details", row=3)
    async def playbook(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if official_frame(self.draft.frame_playbook) == "THE PRINCE":
            from girlframe.discord_adapter.fanbase import FanbaseView

            view = FanbaseView(self)
            await view.render(interaction)
        elif self.draft.girl_playbook == "VATGROWN":
            await interaction.response.send_modal(DetailsModal(self, assets=False, playbook=True))
        else:
            await reply(
                interaction, "No owner-authored details are available for these playbooks yet."
            )

    @discord.ui.button(label="NPC Bonds", row=4)
    async def npc(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        from girlframe.discord_adapter.npc_bonds import NpcView

        await NpcView(self).render(interaction)

    @discord.ui.button(label="Frame setup", row=4)
    async def frame_details(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        baseline = self.draft.frame_setup
        assert baseline is not None
        lines = ["**Verified starting Frame facts — draft only**", clean(baseline.frame)]
        if baseline.harpy_core:
            lines.append("Separate unnamed Harpy Core: " + ", ".join(baseline.harpy_core.tags))
        if baseline.obsolescence_capacity:
            lines.append(f"Obsolescence capacity: {baseline.obsolescence_capacity} boxes.")
        if baseline.starvation_levels:
            lines.append("Starvation levels: " + ", ".join(baseline.starvation_levels))
        if baseline.intrinsic_assets:
            lines.append("Additional fixed Asset: " + ", ".join(baseline.intrinsic_assets))
        if baseline.am_roles:
            lines.append("AM roles: " + ", ".join(baseline.am_roles))
            lines.append(
                "Default: four assigned to you, one to another Girl; actual assignment pending."
            )
        court = next((x for x in self.progress.shared_choices if x.kind == "court"), None)
        if court:
            lines.extend(role + ": player " + str(user) for role, user in court.allocation.items())
        lines.extend(
            "Pending: " + x
            for x in baseline.pending
            if not (court and x.startswith("Choose external AM"))
        )
        lines.append(
            "Use the controls below to continue. Save progress persists these facts; no Plays run."
        )
        await interaction.response.edit_message(
            content="\n".join(lines), view=self, allowed_mentions=discord.AllowedMentions.none()
        )

    @discord.ui.button(label="Save progress", style=discord.ButtonStyle.primary, row=4)
    async def save(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.interaction_check(interaction):
            return
        if not await action_gate(interaction, "metadata"):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        submitted, previous = self.draft, self.progress
        try:
            result = await asyncio.to_thread(
                self.service.save,
                viewer_from_interaction(interaction),
                str(interaction.id),
                previous.revision,
                previous.character_revision,
                submitted,
                expected_pair_token=previous.pair_choice.token if previous.pair_choice else None,
            )
            self.progress = CreationProgress(
                result["revision"],
                previous.character_revision,
                submitted,
                pair_choice=previous.pair_choice,
                shared_choices=previous.shared_choices,
            )
            self.generation += 1
            prefix = "Progress saved.\n"
            if self.draft != submitted:
                prefix += "Newer edits below still need saving.\n"
            await self.render(interaction, prefix)
        except WorkflowError as error:
            await reply(interaction, str(error))
        except Exception:
            await reply(
                interaction,
                "Could not confirm this save. Reopen /character build to check saved progress.",
            )


def register_creation(
    tree: app_commands.CommandTree, guild_id: int, service: CreationService
) -> None:
    character = tree.get_command("character", guild=discord.Object(id=guild_id))
    assert isinstance(character, app_commands.Group)

    @character.command(name="build", description="Choose and save starting Assets and appearance")
    async def build(interaction: discord.Interaction) -> None:
        if not await action_gate(interaction, "metadata"):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            progress = await asyncio.to_thread(service.get, viewer_from_interaction(interaction))
            view = CreationView(service, interaction.user.id, progress)
            prefix = (
                "Playbooks changed. Choose Assets again; prior saved progress remains in history.\n"
                if progress.playbooks_changed
                else ""
            )
            await view.render(interaction, prefix)
        except (WorkflowError, ValidationError) as error:
            await reply(
                interaction,
                str(error) if isinstance(error, WorkflowError) else "Creation data needs review.",
            )
        except Exception:
            await reply(
                interaction, "Creation unavailable. Ask an administrator to check migrations."
            )
