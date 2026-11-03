"""Private paged review of saved choices, never a playable-sheet activation."""

import asyncio
from typing import Any
from uuid import uuid4

import discord
from discord import app_commands

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.creation import clean
from girlframe.discord_adapter.onboarding import action_gate, reply
from girlframe.engine.bonds import starting_kind
from girlframe.engine.npc_bonds import NPC_ROLES
from girlframe.services.creation_review import CreationReviewService, CurrentReview
from girlframe.services.onboarding import WorkflowError

SECTIONS = ("Validation", "Assets", "Appearance", "Relationships", "Frame and resources")


def pages(review: CurrentReview, section: str) -> list[str]:
    sheet = review.sheet
    draft = sheet.creation
    if section == "Validation":
        lines = [
            "Ready for independent rules review."
            if sheet.ready_for_rules_review
            else "Creation needs work:",
            *("• " + issue.message for issue in sheet.issues),
            "Save review snapshot records saved choices only. It does not activate gameplay.",
        ]
    elif section == "Assets":
        girl_assets = (
            draft.pair_asset_descriptions if draft.girl_playbook == "BONDED" else draft.girl_assets
        )
        lines = [
            "Girl Assets:",
            *(x.name + ": " + (x.description or "description missing") for x in girl_assets),
            "Frame Assets:",
            *(x.name + ": " + (x.description or "description missing") for x in draft.frame_assets),
        ]
        if draft.void_asset:
            lines.append("Void-altered: " + draft.void_asset)
        if draft.intrinsic_frame_assets:
            lines.append("Additional fixed Asset: " + ", ".join(draft.intrinsic_frame_assets))
    elif section == "Appearance":
        lines = [
            "Current callsign: " + sheet.callsign,
            "Callsign at activation: " + sheet.activation_callsign,
            "Frame name: " + draft.frame_name,
            "Girl: " + draft.girl_appearance,
            "Frame: " + draft.frame_appearance,
            "Identities: " + ", ".join(draft.identities),
        ]
        if draft.dna_basis:
            lines.append("DNA basis: " + draft.dna_basis)
        if draft.fanbase:
            fan = draft.fanbase
            lines.extend(
                (
                    "Fan demographics: " + ", ".join(fan.additional_identities),
                    "Demanded: " + ", ".join(fan.label(x) for x in fan.demanded),
                    "Rejected: " + ", ".join(fan.label(x) for x in fan.rejected),
                )
            )
    elif section == "Relationships":
        lines = [
            f"{x.depth} Bond with player {x.counterpart} "
            f"({'outgoing' if x.outgoing else 'incoming'}): {x.context or 'no shared context'}"
            for x in sheet.bonds
        ]
        lines.extend(
            NPC_ROLES[draft.girl_playbook][x.slot]
            + ": "
            + (x.name or "unnamed")
            + "\n"
            + x.feelings
            for x in draft.npc_bonds
        )
        lines.extend(
            ("Court assignment: " if x.kind == "court" else "Mentor callsign: ") + x.value
            for x in sheet.shared
        )
        lines.extend(
            f"Received Court role: {x.value} from player {x.source_id}"
            for x in sheet.received_court
        )
        lines.extend(
            f"Player {x.user_id}: {x.missions} shared missions" for x in draft.prior_missions
        )
        if draft.girl_playbook == "NEWGIRL":
            lines.append("Cadre discussion confirmed: " + str(draft.cadre_discussed))
        if not lines:
            lines = ["No current relationship choices."]
    else:
        lines = [
            "Starting Status: " + (sheet.status or "unresolved"),
            "Starting access (book PDF 7):",
            *sheet.access,
        ]
        if sheet.rulings:
            rules = sheet.rulings
            lines.extend(
                (
                    "Campaign rulings — not printed starting defaults:",
                    "Provenance: " + rules.provenance,
                    f"Heat {rules.starting_heat}; CONSUME {rules.consume_hunger}; "
                    f"DoctorDoctor {rules.obsolescence_marked} marked boxes.",
                    "Requisition mode: " + rules.requisition_mode,
                )
            )
        else:
            lines.append(
                "Starting resource values unresolved: Handler must confirm campaign rulings."
            )
        baseline = draft.frame_setup
        if baseline:
            if baseline.harpy_core:
                lines.append("Separate unnamed Harpy Core: " + ", ".join(baseline.harpy_core.tags))
            if baseline.obsolescence_capacity:
                lines.append(f"Obsolescence capacity: {baseline.obsolescence_capacity}")
            if baseline.starvation_levels:
                lines.append("Starvation levels: " + ", ".join(baseline.starvation_levels))
            court = next(
                (x for x in sheet.shared if x.kind == "court" and x.source_id == sheet.owner), None
            )
            if court:
                lines.extend(f"{role}: player {uid}" for role, uid in court.allocation.items())
    text = "\n\n".join(clean(x) for x in lines)
    return [text[start : start + 3600] for start in range(0, len(text), 3600)] or [
        "No choices saved."
    ]


class SectionSelect(discord.ui.Select["ReviewView"]):
    def __init__(self, parent: "ReviewView"):
        self.parent_view = parent
        super().__init__(
            placeholder="Review a sheet section",
            row=0,
            options=[
                discord.SelectOption(label=x, value=x, default=x == parent.section)
                for x in SECTIONS
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.parent_view.section, self.parent_view.page_index = self.values[0], 0
        await self.parent_view.reload(interaction)


class StartingBondSelect(discord.ui.Select["ReviewView"]):
    def __init__(self, parent: "ReviewView", current: CurrentReview):
        self.parent_view, self.snapshot = parent, current
        girl = current.sheet.creation.girl_playbook
        options = [
            x
            for x in current.sheet.bonds
            if x.depth == starting_kind(girl) and (girl not in ("NEWGIRL", "BONDED") or x.outgoing)
        ]
        super().__init__(
            placeholder="Choose your starting Bond for review",
            row=3,
            options=[
                discord.SelectOption(
                    label="Clear explicit choice; use own proposal if eligible", value="clear"
                )
            ]
            + [
                discord.SelectOption(
                    label=f"{x.depth} — player {x.counterpart}",
                    value=x.id,
                    default=x.id == current.sheet.creation.starting_bond_id,
                )
                for x in options[:24]
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        identity = self.values[0]
        if not any(x.value == identity for x in self.options):
            await reply(interaction, "Choose a Bond from this review.")
            return
        await interaction.response.edit_message(
            content=(
                "Clear your explicit starting Bond choice?"
                if identity == "clear"
                else "Count this accepted agreement as your starting Bond? "
                "Review the relationship before confirming."
            )
            + " This changes your draft only.",
            embed=None,
            view=ConfirmBond(self.parent_view, self.snapshot, identity),
            allowed_mentions=discord.AllowedMentions.none(),
        )


class ConfirmBond(discord.ui.View):
    def __init__(self, parent: "ReviewView", current: CurrentReview, identity: str):
        super().__init__(timeout=600)
        self.parent, self.current, self.identity = parent, current, identity

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await self.parent.interaction_check(interaction)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]
    ) -> None:
        await reply(interaction, "Selection unavailable. Reopen /character review.")

    @discord.ui.button(label="Confirm starting Bond", style=discord.ButtonStyle.primary)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if not await self.interaction_check(interaction) or not await action_gate(
            interaction, "metadata"
        ):
            return
        await interaction.response.defer()
        sheet = self.current.sheet
        try:
            await asyncio.to_thread(
                self.parent.service.select_bond,
                viewer_from_interaction(interaction),
                str(interaction.id),
                sheet.creation_revision,
                sheet.character_revision,
                sheet.creation,
                None if self.identity == "clear" else self.identity,
            )
            await self.parent.present(
                interaction, "Starting Bond selected. Draft remains inactive."
            )
        except WorkflowError as error:
            await self.parent.present(interaction, str(error))

    @discord.ui.button(label="Back to review")
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if await self.interaction_check(interaction):
            await interaction.response.defer()
            await self.parent.present(interaction)


class ReviewView(discord.ui.View):
    def __init__(self, service: CreationReviewService, owner: int):
        super().__init__(timeout=600)
        self.service, self.owner = service, owner
        self.current: CurrentReview | None = None
        self.section, self.page_index = "Validation", 0
        self.page_count = 1
        self.nonce = uuid4().hex[:12]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "This sheet review belongs to another player.")
            return False
        try:
            await asyncio.to_thread(self.service.get, viewer_from_interaction(interaction))
            return True
        except WorkflowError as error:
            await reply(interaction, str(error))
            return False

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]
    ) -> None:
        await reply(
            interaction, "Review unavailable. Reopen /character review to check saved data."
        )

    async def present(self, interaction: discord.Interaction, notice: str = "") -> None:
        self.current = await asyncio.to_thread(
            self.service.get, viewer_from_interaction(interaction)
        )
        self.save.custom_id = (
            f"review:{self.nonce}:{self.current.saved_revision}:{self.current.fingerprint[:32]}"
        )
        content = pages(self.current, self.section)
        self.page_count = len(content)
        self.page_index = min(max(0, self.page_index), self.page_count - 1)
        self.previous.disabled = self.page_index == 0
        self.next.disabled = self.page_index == self.page_count - 1
        for child in list(self.children):
            if isinstance(child, discord.ui.Select):
                self.remove_item(child)
        self.add_item(SectionSelect(self))
        girl = self.current.sheet.creation.girl_playbook
        if self.current.sheet.creation.starting_bond_id is not None or any(
            x.depth == starting_kind(girl) and (girl not in ("NEWGIRL", "BONDED") or x.outgoing)
            for x in self.current.sheet.bonds
        ):
            self.add_item(StartingBondSelect(self, self.current))
        embed = discord.Embed(
            title="Character sheet review — draft",
            description=content[self.page_index],
            color=0x9F96FF,
        )
        embed.add_field(
            name="Saved review",
            value=f"Revision {self.current.saved_revision} · "
            + ("current" if self.current.saved_current else "not saved or needs refresh"),
            inline=False,
        )
        if notice:
            embed.add_field(name="Update", value=clean(notice)[:1024], inline=False)
        embed.set_footer(
            text=f"{self.section} · Page {self.page_index + 1}/{self.page_count}"
            " · Private · Gameplay inactive"
        )
        await interaction.edit_original_response(
            content=None, embed=embed, view=self, allowed_mentions=discord.AllowedMentions.none()
        )

    async def reload(self, interaction: discord.Interaction) -> None:
        if not await action_gate(interaction, "inbox_read"):
            return
        await interaction.response.defer()
        await self.present(interaction)

    @discord.ui.button(label="Previous", row=1)
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        self.page_index -= 1
        await self.reload(interaction)

    @discord.ui.button(label="Next", row=1)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        self.page_index += 1
        await self.reload(interaction)

    @discord.ui.button(label="Refresh", row=1)
    async def refresh(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await self.reload(interaction)

    @discord.ui.button(label="Save review snapshot", style=discord.ButtonStyle.primary, row=2)
    async def save(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        current = self.current
        if (
            current is None
            or not await self.interaction_check(interaction)
            or not await action_gate(interaction, "metadata")
        ):
            return
        if (
            not isinstance(interaction.data, dict)
            or interaction.data.get("custom_id") != button.custom_id
        ):
            await interaction.response.defer()
            await self.present(
                interaction, "This control belongs to an older review. Check the current sheet."
            )
            return
        await interaction.response.defer()
        try:
            result = await asyncio.to_thread(
                self.service.save,
                viewer_from_interaction(interaction),
                str(interaction.id),
                current.saved_revision,
                current.fingerprint,
            )
            await self.present(
                interaction,
                f"Review snapshot {result['revision']} saved privately. Gameplay remains inactive.",
            )
        except WorkflowError as error:
            await self.present(interaction, str(error))

    @discord.ui.button(label="Activation awaiting rules review", row=2, disabled=True)
    async def activate(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if await self.interaction_check(interaction):
            try:
                await asyncio.to_thread(self.service.activate, viewer_from_interaction(interaction))
            except WorkflowError as error:
                await reply(interaction, str(error))

    @discord.ui.button(label="Close", row=1)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if await self.interaction_check(interaction):
            await interaction.response.edit_message(
                content="Review closed. Reopen /character review to resume.", embed=None, view=None
            )
            self.stop()


def register_creation_review(
    tree: app_commands.CommandTree, guild_id: int, service: CreationReviewService
) -> None:
    character = tree.get_command("character", guild=discord.Object(id=guild_id))
    assert isinstance(character, app_commands.Group)

    @character.command(
        name="review", description="Validate saved creation and review your private draft sheet"
    )
    async def review(interaction: discord.Interaction) -> None:
        if not await action_gate(interaction, "metadata"):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await ReviewView(service, interaction.user.id).present(interaction)
        except WorkflowError as error:
            await reply(interaction, str(error))
