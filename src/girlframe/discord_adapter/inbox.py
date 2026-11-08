"""Private overview and guided request review. Mutations stay in existing services."""

import asyncio
import hashlib
from typing import Any, cast
from uuid import uuid4

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.creation import clean
from girlframe.discord_adapter.onboarding import action_gate, reply
from girlframe.engine.creation_details import Role
from girlframe.engine.inbox import CATEGORIES, InboxItem, InboxPage
from girlframe.services.inbox import InboxService
from girlframe.services.onboarding import WorkflowError

CATEGORY_LABELS = {
    "all": "All request types",
    "missions": "Mission offers & consequences",
    "off_duty": "Off-Duty, recovery & Strain",
    "world": "World & NPC roles",
    "plays": "Pending Plays",
    "bonds": "Starting Bonds",
    "mentors": "Mentor coordination",
    "court": "Red Queen's Court",
    "pair": "Pair agreements & Assets",
    "playbook": "Standards, maxims & Investors",
}


class CategorySelect(discord.ui.Select["InboxView"]):
    def __init__(self, parent: "InboxView"):
        self.parent_view = parent
        super().__init__(
            placeholder="Filter request types",
            row=1,
            options=[
                discord.SelectOption(
                    label=CATEGORY_LABELS[key], value=key, default=key == parent.category
                )
                for key in CATEGORIES
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.parent_view.reload(interaction, category=self.values[0])


class RequestSelect(discord.ui.Select["InboxView"]):
    def __init__(self, parent: "InboxView", items: tuple[InboxItem, ...]):
        self.parent_view, self.snapshot = parent, items
        super().__init__(
            placeholder="Choose a request to review",
            row=2,
            options=[
                discord.SelectOption(
                    label=(x.title + " · " + x.counterpart)[:100],
                    value=x.key,
                    description="Changed — review needed"
                    if x.stale
                    else x.state.capitalize()
                    if x.state != "pending"
                    else "Your next step"
                    if x.task
                    else "Needs your decision"
                    if x.incoming
                    else "Waiting on the other player",
                )
                for x in items
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await action_gate(interaction, "inbox_read"):
            return
        chosen = next((x for x in self.snapshot if x.key == self.values[0]), None)
        if chosen is None:
            await reply(interaction, "Select a request from this inbox page.")
            return
        parent = self.parent_view
        parent.overview = False
        parent.focus_key, parent.focus_revision = chosen.key, chosen.revision
        await interaction.response.defer()
        try:
            await parent.present(interaction)
        except WorkflowError as error:
            parent.overview = True
            parent.focus_key, parent.focus_revision = None, None
            await parent.present(interaction, str(error))


class InboxView(discord.ui.View):
    def __init__(self, service: InboxService, owner: int):
        super().__init__(timeout=600)
        self.service, self.owner = service, owner
        self.scope, self.category, self.index = "pending", "all", 0
        self.page: InboxPage | None = None
        self.nonce, self.generation = uuid4().hex[:12], 0
        self.overview = True
        self.focus_key: str | None = None
        self.focus_revision: int | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "This inbox belongs to another player.")
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
            interaction, "Inbox unavailable. Reopen /character requests to check saved data."
        )

    def controls(self) -> None:
        assert self.page is not None
        for child in list(self.children):
            if isinstance(child, discord.ui.Select) or child in (
                self.primary,
                self.secondary,
                self.back,
            ):
                self.remove_item(child)
        self.add_item(CategorySelect(self))
        for key, button in (
            ("pending", self.pending),
            ("you", self.you),
            ("waiting", self.waiting),
            ("history", self.history),
        ):
            button.style = (
                discord.ButtonStyle.primary if key == self.scope else discord.ButtonStyle.secondary
            )
        self.previous.disabled = self.page.index < 5 if self.overview else self.page.index == 0
        self.next.disabled = (
            self.page.index + 5 >= self.page.total
            if self.overview
            else self.page.index >= self.page.total - 1
        )
        if self.overview and self.page.window:
            self.add_item(RequestSelect(self, self.page.window))
        if not self.overview:
            self.add_item(self.back)
        item = self.page.item
        self.generation += 1
        if item:
            digest = hashlib.sha256(item.key.encode()).hexdigest()[:16]
            for name, button in (("primary", self.primary), ("secondary", self.secondary)):
                button.custom_id = (
                    f"requests:{self.nonce}:{self.generation}:{name}:{digest}:{item.revision}"
                )
        if not self.overview and item and item.primary:
            self.primary.label = item.primary
            self.primary.disabled = item.stale
            self.primary.style = (
                discord.ButtonStyle.primary if item.task else discord.ButtonStyle.success
            )
            self.add_item(self.primary)
        if not self.overview and item and item.secondary:
            self.secondary.label = "Decline" if item.secondary == "decline" else "Withdraw"
            self.secondary.style = discord.ButtonStyle.danger
            self.add_item(self.secondary)

    def embed(self, notice: str = "") -> discord.Embed:
        assert self.page is not None
        page = self.page
        counts = page.counts
        description = (
            f"{counts['pending']} pending · {counts['you']} need you · {counts['waiting']} waiting"
        )
        if notice:
            description += "\n" + clean(notice)
        item = page.item
        embed = discord.Embed(
            title=item.title if item and not self.overview else "Your requests",
            description=description,
            colour=0x9F96FF,
        )
        if not item:
            embed.add_field(
                name="You're caught up in this view",
                value="Try another filter or Refresh. Saved history is retained.",
                inline=False,
            )
        elif self.overview:
            for offset, entry in enumerate(page.window):
                status = (
                    "Changed — review needed"
                    if entry.stale
                    else "Your next step"
                    if entry.task
                    else entry.state.capitalize()
                    if entry.state != "pending"
                    else "Needs you"
                    if entry.incoming
                    else "Waiting"
                )
                embed.add_field(
                    name=f"{(page.index // 5) * 5 + offset + 1}. {entry.title}",
                    value=clean(entry.counterpart) + " · " + status,
                    inline=False,
                )
        else:
            relation = "With" if item.task else "From" if item.incoming else "To"
            embed.add_field(name=relation, value=clean(item.counterpart), inline=True)
            status = (
                "Changed — new review required"
                if item.stale
                else "Your next step"
                if item.task
                else "Needs your decision"
                if item.state == "pending" and item.incoming
                else "Waiting on the other player"
                if item.state == "pending"
                else item.state.capitalize()
            )
            embed.add_field(name="Status", value=status, inline=True)
            embed.add_field(
                name="What this action changes", value=clean(item.effect)[:1024], inline=False
            )
            embed.add_field(
                name="Details shared with you", value=clean(item.details)[:1024], inline=False
            )
            if item.stale:
                embed.add_field(
                    name="This version cannot be accepted",
                    value="Profiles or authority changed. Send a fresh proposal; "
                    "Refresh cannot authorize the old version.",
                    inline=False,
                )
            if item.state == "pending" and not item.incoming:
                embed.add_field(
                    name="Your role",
                    value=(
                        "You sent this version. Withdraw and recreate it with current profiles."
                        if item.stale
                        else "You sent this request. The recipient decides; you can withdraw it."
                    ),
                    inline=False,
                )
        position = (
            f"Page {page.index // 5 + 1} of {max(1, (page.total + 4) // 5)} · {page.total} items"
            if self.overview
            else f"Request {page.index + 1 if item else 0} of {page.total}"
        )
        embed.set_footer(text=position + f" · {CATEGORY_LABELS[self.category]} · Private inbox")
        return embed

    async def present(self, interaction: discord.Interaction, notice: str = "") -> None:
        self.page = await asyncio.to_thread(
            self.service.page,
            viewer_from_interaction(interaction),
            self.scope,
            self.category,
            self.index,
            selected_key=self.focus_key,
            expected_revision=self.focus_revision,
        )
        self.index = self.page.index
        self.controls()
        await interaction.edit_original_response(
            content=None,
            embed=self.embed(notice),
            view=self,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def reload(
        self,
        interaction: discord.Interaction,
        scope: str | None = None,
        step: int = 0,
        category: str | None = None,
    ) -> None:
        if not await action_gate(interaction, "inbox_read"):
            return
        self.focus_key, self.focus_revision = None, None
        if category is not None:
            self.category, self.index, self.overview = category, 0, True
        if scope is not None:
            self.scope, self.index, self.overview = scope, 0, True
        self.index = max(0, self.index + step)
        await interaction.response.defer()
        await self.present(interaction)

    @discord.ui.button(label="Pending", row=0)
    async def pending(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await self.reload(interaction, "pending")

    @discord.ui.button(label="Needs you", row=0)
    async def you(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        await self.reload(interaction, "you")

    @discord.ui.button(label="Waiting", row=0)
    async def waiting(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await self.reload(interaction, "waiting")

    @discord.ui.button(label="History", row=0)
    async def history(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await self.reload(interaction, "history")

    async def fresh_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> bool:
        data = interaction.data
        if not isinstance(data, dict) or data.get("custom_id") != button.custom_id:
            await interaction.response.defer()
            await self.present(
                interaction, "This button belongs to an older view. Review the current request."
            )
            return False
        return True

    @discord.ui.button(label="Continue", row=2)
    async def primary(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if self.page is None or self.page.item is None:
            return
        item = self.page.item
        if not await self.interaction_check(interaction) or not await action_gate(
            interaction, "metadata"
        ):
            return
        if not await self.fresh_button(interaction, button):
            return
        await interaction.response.defer()
        try:
            if item.task:
                current = await asyncio.to_thread(
                    self.service.current,
                    viewer_from_interaction(interaction),
                    item.key,
                    item.revision,
                )
                await self.route(interaction, current)
                return
            await asyncio.to_thread(
                self.service.decide,
                viewer_from_interaction(interaction),
                str(interaction.id),
                item,
                "accept",
            )
            self.overview = True
            self.focus_key, self.focus_revision = None, None
            self.index = (self.index // 5) * 5
            await self.present(interaction, "Decision saved. Queue refreshed.")
        except WorkflowError as error:
            self.overview = True
            self.focus_key, self.focus_revision = None, None
            await self.present(interaction, str(error))

    @discord.ui.button(label="Decline", row=2)
    async def secondary(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if self.page is None or self.page.item is None:
            return
        item = self.page.item
        if item.secondary not in ("decline", "withdraw"):
            return
        if not await self.interaction_check(interaction) or not await action_gate(
            interaction, "metadata"
        ):
            return
        if not await self.fresh_button(interaction, button):
            return
        await interaction.response.defer()
        try:
            await asyncio.to_thread(
                self.service.decide,
                viewer_from_interaction(interaction),
                str(interaction.id),
                item,
                "decline" if item.secondary == "decline" else "withdraw",
            )
            self.overview = True
            self.focus_key, self.focus_revision = None, None
            self.index = (self.index // 5) * 5
            await self.present(interaction, "Decision saved. Queue refreshed.")
        except WorkflowError as error:
            self.overview = True
            self.focus_key, self.focus_revision = None, None
            await self.present(interaction, str(error))

    @discord.ui.button(label="Previous", row=3)
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await self.reload(interaction, step=-5 if self.overview else -1)

    @discord.ui.button(label="Next", row=3)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        await self.reload(interaction, step=5 if self.overview else 1)

    @discord.ui.button(label="Refresh", row=3)
    async def refresh(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await self.reload(interaction)

    @discord.ui.button(label="Back to inbox", row=4)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        self.overview = True
        self.index = (self.index // 5) * 5
        await self.reload(interaction)

    @discord.ui.button(label="Close", row=3)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.interaction_check(interaction):
            return
        await interaction.response.edit_message(
            content="Inbox closed. Reopen /character requests to resume. Saved data is retained.",
            embed=None,
            view=None,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.stop()

    async def route(self, interaction: discord.Interaction, item: InboxItem) -> None:
        viewer = viewer_from_interaction(interaction)

        async def open_child(text: str, child: discord.ui.View) -> None:
            back = InboxBackButton(self)
            child.add_item(back)
            await interaction.edit_original_response(
                content=text,
                embed=None,
                view=child,
                allowed_mentions=discord.AllowedMentions.none(),
            )

        if item.task in ("m3_director_review", "m3_director_context"):
            from girlframe.discord_adapter.m3_director import open_context, open_review
            from girlframe.services.m3_director import DirectorService
            from girlframe.services.m3_missions import MissionService

            function = open_review if item.task == "m3_director_review" else open_context
            await function(
                interaction, DirectorService(MissionService(self.service.store)), item.identity
            )
        elif item.task == "m3_npc_role":
            from girlframe.discord_adapter.m3_npc_roles import open_invitation
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_npc_roles import NpcRoleService
            from girlframe.services.m3_world import WorldService

            await open_invitation(
                interaction,
                NpcRoleService(WorldService(MissionService(self.service.store))),
                item.identity,
            )
        elif item.task == "m3_repair_quote":
            from girlframe.discord_adapter.m3_repairs import open_quote
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_repairs import RepairService

            await open_quote(
                interaction,
                RepairService(OffDutyService(MissionService(self.service.store))),
                item.identity,
            )
        elif item.task == "m3_observation":
            from girlframe.discord_adapter.m3_observation import open_work as open_observation
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_observation import ObservationService
            from girlframe.services.m3_off_duty import OffDutyService

            await open_observation(
                interaction,
                ObservationService(OffDutyService(MissionService(self.service.store))),
                item.identity,
            )
        elif item.task == "m3_frame_reward":
            from girlframe.discord_adapter.m3_frame_rewards import open_reward
            from girlframe.services.m3_frame_rewards import RewardService
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService

            await open_reward(
                interaction,
                RewardService(OffDutyService(MissionService(self.service.store))),
                item.identity,
            )
        elif item.task == "m3_off_duty":
            from girlframe.discord_adapter.m3_off_duty import open_period
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService

            await open_period(interaction, OffDutyService(MissionService(self.service.store)))
        elif item.task == "m3_collective_tag":
            from girlframe.discord_adapter.m3_collective_handler_tags import open_collective
            from girlframe.services.m3_collective_handler_tags import CollectiveTagService

            await open_collective(
                interaction, CollectiveTagService(self.service.store), item.identity
            )
        elif item.task == "m3_alpha_consent":
            from girlframe.discord_adapter.m3_alpha_sex import open_consent
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_alpha_sex import SexService

            await open_consent(
                interaction, SexService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_am_source":
            from girlframe.discord_adapter.m3_am import open_source
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_am_scrutinized import ScrutinyService

            await open_source(
                interaction, ScrutinyService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_am_jailbroken":
            from girlframe.discord_adapter.m3_am_jailbroken import open_jailbroken
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_am_jailbroken import JailbrokenService

            await open_jailbroken(
                interaction, JailbrokenService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_am_branch":
            from girlframe.discord_adapter.m3_am_branch import open_branch
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_am_branch import BranchService

            await open_branch(
                interaction, BranchService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_am_body":
            from girlframe.discord_adapter.m3_am_body import open_body
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_am_body import BodyService

            await open_body(
                interaction, BodyService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_am_code_source":
            from girlframe.discord_adapter.m3_am_code import open_source as open_am_code
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_am_code import CodeService

            await open_am_code(
                interaction, CodeService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_physiotherapist":
            from girlframe.discord_adapter.m3_physiotherapist import open_request as open_therapy
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_physiotherapist import PhysiotherapistService

            await open_therapy(
                interaction, PhysiotherapistService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_martyr":
            from girlframe.discord_adapter.m3_martyr import open_memorial
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_martyr import MartyrService

            await open_memorial(
                interaction, MartyrService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_budget_cleanup":
            from girlframe.discord_adapter.m3_budget_cleanup import open_cleanup
            from girlframe.services.m3_budget_cleanup import CleanupService

            await open_cleanup(interaction, CleanupService(self.service.store), item.identity)
        elif item.task == "m3_budget_anarchy":
            from girlframe.discord_adapter.m3_budget_anarchy import open_anarchy
            from girlframe.services.m3_budget_anarchy import AnarchyService

            await open_anarchy(interaction, AnarchyService(self.service.store), item.identity)
        elif item.task == "m3_budget_candidate":
            from girlframe.discord_adapter.m3_budget_candidate import open_candidate
            from girlframe.services.m3_budget_candidate import CandidateService

            await open_candidate(interaction, CandidateService(self.service.store), item.identity)
        elif item.task == "m3_budget_director":
            from girlframe.discord_adapter.m3_budget_director import open_meeting
            from girlframe.services.m3_budget_director import MeetingService

            await open_meeting(interaction, MeetingService(self.service.store), item.identity)
        elif item.task == "m3_budget_storage":
            from girlframe.discord_adapter.m3_budget_storage import (
                open_storage as open_budget_storage,
            )
            from girlframe.services.m3_budget_storage import StorageService as BudgetStorageService

            await open_budget_storage(
                interaction, BudgetStorageService(self.service.store), item.identity
            )
        elif item.task == "m3_rebel_contact":
            from girlframe.discord_adapter.m3_rebel_contact import open_contact
            from girlframe.services.m3_rebel_contact import ContactService

            await open_contact(interaction, ContactService(self.service.store), item.identity)
        elif item.task == "m3_budget_fight":
            from girlframe.discord_adapter.m3_budget_fight import open_fight
            from girlframe.services.m3_budget_fight import FightService

            await open_fight(interaction, FightService(self.service.store), item.identity)
        elif item.task == "m3_budget_assassination":
            from girlframe.discord_adapter.m3_budget_assassination import open_assignment
            from girlframe.services.m3_budget_assassination import AssassinationService

            await open_assignment(
                interaction, AssassinationService(self.service.store), item.identity
            )
        elif item.task == "m3_budget_visitor":
            from girlframe.discord_adapter.m3_budget_visitor import open_visit
            from girlframe.services.m3_budget_visitor import VisitorService

            await open_visit(interaction, VisitorService(self.service.store), item.identity)
        elif item.task == "m3_political_function":
            from girlframe.discord_adapter.m3_political_function import open_function
            from girlframe.services.m3_political_function import FunctionService

            await open_function(interaction, FunctionService(self.service.store), item.identity)
        elif item.task == "m3_budget_patron":
            from girlframe.discord_adapter.m3_budget_patron import open_patron
            from girlframe.services.m3_budget_patron import PatronService

            await open_patron(interaction, PatronService(self.service.store), item.identity)
        elif item.task == "m3_special_girl":
            from girlframe.discord_adapter.m3_special_girl import open_token
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_special_girl import SpecialGirlService

            await open_token(
                interaction, SpecialGirlService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_handler_pr":
            from girlframe.discord_adapter.m3_handler_pr import open_pr
            from girlframe.services.m3_handler_pr import HandlerPRService

            await open_pr(interaction, HandlerPRService(self.service.store), item.identity)
        elif item.task == "m3_npc_bond_play":
            from girlframe.discord_adapter.m3_npc_bond_play import open_npc_bond_play
            from girlframe.services.m3_npc_bond_play import NpcBondPlayService

            await open_npc_bond_play(
                interaction, NpcBondPlayService(self.service.store), item.identity
            )
        elif item.task == "m3_ankou_feedback":
            from girlframe.discord_adapter.m3_ankou_feedback import open_feedback
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_ankou_feedback import FeedbackService

            await open_feedback(
                interaction, FeedbackService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_disposable_psyche":
            from girlframe.discord_adapter.m3_disposable_psyche import open_psyche
            from girlframe.services.m3_disposable_psyche import PsycheService

            await open_psyche(interaction, PsycheService(self.service.store), item.identity)
        elif item.task == "m3_princess_sex":
            from girlframe.discord_adapter.m3_princess_sex import open_princess
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_princess_sex import SexService as PrincessSexService

            await open_princess(
                interaction, PrincessSexService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_dose_up":
            from girlframe.discord_adapter.m3_dose_up import open_dose_up
            from girlframe.services.m3_dose_up import DoseUpService

            await open_dose_up(interaction, DoseUpService(self.service.store), item.identity)
        elif item.task == "m3_promotional_opportunity":
            from girlframe.discord_adapter.m3_promotional_opportunity import open_opportunity
            from girlframe.services.m3_promotional_opportunity import PromotionalOpportunityService

            await open_opportunity(
                interaction, PromotionalOpportunityService(self.service.store), item.identity
            )
        elif item.task == "m3_intracadre_marriage":
            from girlframe.discord_adapter.m3_intracadre_marriage import open_marriage
            from girlframe.services.m3_intracadre_marriage import MarriageService

            await open_marriage(interaction, MarriageService(self.service.store), item.identity)
        elif item.task == "m3_gender_designation":
            from girlframe.discord_adapter.m3_gender_designation import open_designation
            from girlframe.services.m3_gender_designation import GenderDesignationService

            await open_designation(
                interaction, GenderDesignationService(self.service.store), item.identity
            )
        elif item.task == "m3_a_bomb":
            from girlframe.discord_adapter.m3_a_bomb import open_bomb
            from girlframe.services.m3_a_bomb import ABombService

            await open_bomb(interaction, ABombService(self.service.store), item.identity)
        elif item.task == "m3_politician_bribery":
            from girlframe.discord_adapter.m3_politician_bribery import open_bribery
            from girlframe.services.m3_politician_bribery import BriberyService

            await open_bribery(interaction, BriberyService(self.service.store), item.identity)
        elif item.task == "m3_ship_base":
            from girlframe.discord_adapter.m3_ship_base import open_ship
            from girlframe.services.m3_ship_base import ShipBaseService

            await open_ship(interaction, ShipBaseService(self.service.store), item.identity)
        elif item.task == "m3_tracker_implants":
            from girlframe.discord_adapter.m3_tracker_implants import open_tracker
            from girlframe.services.m3_tracker_implants import TrackerService

            await open_tracker(interaction, TrackerService(self.service.store), item.identity)
        elif item.task == "m3_contaminant_zone":
            from girlframe.discord_adapter.m3_contaminant_zone import open_zone
            from girlframe.services.m3_contaminant_zone import ContaminantZoneService

            await open_zone(interaction, ContaminantZoneService(self.service.store), item.identity)
        elif item.task == "m3_reign_terror":
            from girlframe.discord_adapter.m3_reign_terror import open_terror
            from girlframe.services.m3_reign_terror import ReignTerrorService

            await open_terror(interaction, ReignTerrorService(self.service.store), item.identity)
        elif item.task == "m3_hidden_sidearm":
            from girlframe.discord_adapter.m3_hidden_sidearm import open_sidearm
            from girlframe.services.m3_hidden_sidearm import HiddenSidearmService

            await open_sidearm(interaction, HiddenSidearmService(self.service.store), item.identity)
        elif item.task == "m3_bomb_collar":
            from girlframe.discord_adapter.m3_bomb_collar import open_collar
            from girlframe.services.m3_bomb_collar import BombCollarService

            await open_collar(interaction, BombCollarService(self.service.store), item.identity)
        elif item.task == "m3_secretary":
            from girlframe.discord_adapter.m3_secretary import open_secretary
            from girlframe.services.m3_secretary import SecretaryService

            await open_secretary(interaction, SecretaryService(self.service.store), item.identity)
        elif item.task == "m3_deep_brain_spikes":
            from girlframe.discord_adapter.m3_deep_brain_spikes import open_spikes
            from girlframe.services.m3_deep_brain_spikes import DeepBrainSpikesService

            await open_spikes(
                interaction, DeepBrainSpikesService(self.service.store), item.identity
            )
        elif item.task == "m3_handler_conversion":
            from girlframe.discord_adapter.m3_handler_conversion import open_conversion
            from girlframe.services.m3_handler_conversion import HandlerConversionService

            await open_conversion(
                interaction, HandlerConversionService(self.service.store), item.identity
            )
        elif item.task == "m3_handler_ordinary":
            from girlframe.discord_adapter.m3_handler_ordinary import open_ordinary
            from girlframe.services.m3_handler_ordinary import HandlerOrdinaryService

            await open_ordinary(
                interaction, HandlerOrdinaryService(self.service.store), item.identity
            )
        elif item.task == "m3_location_build":
            from girlframe.discord_adapter.m3_location_build import open_build
            from girlframe.services.m3_location_build import LocationBuildService

            await open_build(interaction, LocationBuildService(self.service.store), item.identity)
        elif item.task == "m3_location_rebuild":
            from girlframe.discord_adapter.m3_location_rebuild import open_rebuild
            from girlframe.services.m3_location_rebuild import LocationRebuildService

            await open_rebuild(
                interaction, LocationRebuildService(self.service.store), item.identity
            )
        elif item.task == "m3_girl_insurance":
            from girlframe.discord_adapter.m3_girl_insurance import open_insurance
            from girlframe.services.m3_girl_insurance import GirlInsuranceService

            await open_insurance(
                interaction, GirlInsuranceService(self.service.store), item.identity
            )
        elif item.task == "m3_cute_uniforms":
            from girlframe.discord_adapter.m3_cute_uniforms import open_uniform
            from girlframe.services.m3_cute_uniforms import CuteUniformService

            await open_uniform(interaction, CuteUniformService(self.service.store), item.identity)
        elif item.task == "m3_budget_removal":
            from girlframe.discord_adapter.m3_budget_removal import open_removal
            from girlframe.services.m3_budget_removal import RemovalService

            await open_removal(interaction, RemovalService(self.service.store), item.identity)
        elif item.task == "m3_supply_drop":
            from girlframe.discord_adapter.m3_supply_drop import open_delivery
            from girlframe.services.m3_supply_drop import SupplyDropService

            await open_delivery(interaction, SupplyDropService(self.service.store), item.identity)
        elif item.task == "m3_budget_departures":
            from girlframe.discord_adapter.m3_budget_departures import open_departures
            from girlframe.services.m3_budget_departures import DepartureService

            await open_departures(interaction, DepartureService(self.service.store), item.identity)
        elif item.task == "m3_handler_advancements":
            from girlframe.discord_adapter.m3_handler_advancements import open_advancement
            from girlframe.services.m3_handler_advancements import HandlerAdvancementService

            await open_advancement(
                interaction, HandlerAdvancementService(self.service.store), item.identity
            )
        elif item.task == "m3_clone_am":
            from girlframe.discord_adapter.m3_clone_am import open_clone
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_clone_am import CloneService

            await open_clone(interaction, CloneService(GameService(self.service.store)))
        elif item.task == "m3_succubus":
            from girlframe.discord_adapter.m3_succubus import open_order
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_succubus import SuccubusService

            await open_order(
                interaction, SuccubusService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_void_retirement":
            from girlframe.discord_adapter.m3_void_retirement import open_offer
            from girlframe.services.m3_void_retirement import StipendService

            await open_offer(interaction, StipendService(self.service.store), item.identity)
        elif item.task == "m3_rebel_leader":
            from girlframe.discord_adapter.m3_rebel_leader import open_leader
            from girlframe.services.m3_rebel_leader import LeaderService

            await open_leader(interaction, LeaderService(self.service.store), item.identity)
        elif item.task == "m3_rebel_merge":
            from girlframe.discord_adapter.m3_rebel_merge import open_merger
            from girlframe.services.m3_rebel_merge import MergerService

            await open_merger(interaction, MergerService(self.service.store), item.identity)
        elif item.task == "m3_budget_ruin":
            from girlframe.discord_adapter.m3_budget_ruin import open_ruin
            from girlframe.services.m3_budget_ruin import RuinService

            await open_ruin(interaction, RuinService(self.service.store), item.identity)
        elif item.task == "m3_budget_tag":
            from girlframe.discord_adapter.m3_budget_tags import open_gift
            from girlframe.services.m3_budget_tags import BudgetTagService

            await open_gift(interaction, BudgetTagService(self.service.store), item.identity)
        elif item.task == "m3_strain_effect":
            from girlframe.discord_adapter.m3_strain_effects import open_effect
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_strain import StrainService
            from girlframe.services.m3_strain_effects import EffectService

            await open_effect(
                interaction,
                EffectService(StrainService(OffDutyService(MissionService(self.service.store)))),
                item.identity,
            )
        elif item.task == "m3_strain":
            from girlframe.discord_adapter.m3_strain import open_work
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_strain import StrainService

            await open_work(
                interaction,
                StrainService(OffDutyService(MissionService(self.service.store))),
                item.identity,
            )
        elif item.task == "m3_off_duty_credit":
            from girlframe.discord_adapter.m3_off_duty import open_credit
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService

            await open_credit(
                interaction, OffDutyService(MissionService(self.service.store)), item.identity
            )
        elif item.task == "m3_replacement":
            from girlframe.discord_adapter.m3_replacement import open_replacement
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_replacement import ReplacementService

            await open_replacement(
                interaction, ReplacementService(MissionService(self.service.store)), item.identity
            )
        elif item.task == "m3_janus_mind":
            from girlframe.discord_adapter.m3_janus_play import open_brain_link
            from girlframe.services.m2_game import GameService

            await open_brain_link(interaction, GameService(self.service.store), item.identity)
        elif item.task == "m3_janus_core":
            from girlframe.discord_adapter.m3_janus import open_core_setup
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_janus import JanusService

            await open_core_setup(
                interaction, JanusService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_janus_pet":
            from girlframe.discord_adapter.m3_janus_requisitions import open_pet
            from girlframe.services.m2_game import GameService

            await open_pet(interaction, GameService(self.service.store), item.identity)
        elif item.task in ("m3_doctor_care", "m3_doctor_procedure"):
            from girlframe.discord_adapter.m3_doctor import open_care
            from girlframe.discord_adapter.m3_doctor import open_request as open_doctor_request
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_doctor import DoctorService

            operation = open_care if item.task == "m3_doctor_care" else open_doctor_request
            await operation(
                interaction, DoctorService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_janus_storage":
            from girlframe.discord_adapter.m3_janus_storage import open_surgery
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_janus_storage import StorageService

            await open_surgery(
                interaction, StorageService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_reaction":
            from girlframe.discord_adapter.m3_reactions import open_reaction
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_reactions import ReactionService

            await open_reaction(
                interaction, ReactionService(MissionService(self.service.store)), item.identity
            )
        elif item.task and item.task.startswith("m3_harpy_task:"):
            from girlframe.discord_adapter.m3_harpy_defeat import open_task as open_harpy_task
            from girlframe.services.m3_harpy_defeat import HarpyDefeatService

            await open_harpy_task(
                interaction,
                HarpyDefeatService(self.service.store),
                item.task.split(":", 1)[1],
                item.identity,
            )
        elif item.task in ("m3_harpy_physical", "m3_harpy_help"):
            from girlframe.discord_adapter.m3_harpy_physical import (
                open_physical,
            )
            from girlframe.discord_adapter.m3_harpy_physical import (
                open_review as open_harpy_review,
            )
            from girlframe.engine.m3_actor_state import ActorRef
            from girlframe.services.m3_harpy_physical import HarpyPhysicalService

            physical_service = HarpyPhysicalService(self.service.store)
            if item.task == "m3_harpy_help":
                await open_harpy_review(interaction, physical_service, item.identity)
            else:
                await open_physical(
                    interaction,
                    physical_service,
                    ActorRef(kind="external_pilot", entity=item.identity),
                )
        elif item.task == "m3_virus_exposure":
            from girlframe.discord_adapter.m3_compliance_virus import (
                open_exposure as open_virus_exposure,
            )
            from girlframe.services.m2_game import GameService

            await open_virus_exposure(interaction, GameService(self.service.store), item.identity)
        elif item.task == "handler_girl_void":
            from girlframe.discord_adapter.m3_handler_girl_void import open_handler_girl_void
            from girlframe.services.m3_handler_girl_void import HandlerGirlVoidService

            await open_handler_girl_void(
                interaction, HandlerGirlVoidService(self.service.store), item.identity
            )
        elif item.task == "sprite_intercept":
            from girlframe.discord_adapter.m3_sprite import open_sprite
            from girlframe.services.m3_sprite import SpriteService

            await open_sprite(interaction, SpriteService(self.service.store), item.identity)
        elif item.task == "handler_void":
            from girlframe.discord_adapter.m3_handler_void import open_handler_void
            from girlframe.services.m3_handler_void import HandlerVoidService

            await open_handler_void(
                interaction, HandlerVoidService(self.service.store), item.identity
            )
        elif item.task == "quadrant_loss":
            from girlframe.discord_adapter.m3_quadrant_loss import open_loss
            from girlframe.services.m3_quadrant_loss import LossService

            await open_loss(interaction, LossService(self.service.store), item.identity)
        elif item.task == "m3_mockingbird":
            from girlframe.discord_adapter.m3_mockingbird_plays import open_request
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_mockingbird_plays import MockingbirdService

            await open_request(
                interaction, MockingbirdService(GameService(self.service.store)), item.identity
            )
        elif item.task == "leviathan_layers":
            from girlframe.discord_adapter.m3_leviathan import open_layers
            from girlframe.services.m3_leviathan import LeviathanService

            await open_layers(interaction, LeviathanService(self.service.store), item.identity)
        elif item.task == "gorgon_dormant_void":
            from girlframe.discord_adapter.m3_gorgon_dormant import open_gorgon_dormant
            from girlframe.services.m3_gorgon_dormant import GorgonDormantService

            await open_gorgon_dormant(
                interaction, GorgonDormantService(self.service.store), item.identity
            )
        elif item.task in ("mockingbird_exposure", "mockingbird_discovery"):
            from girlframe.discord_adapter.m3_mockingbird_discovery import (
                open_discovery,
                open_exposure,
            )
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_mockingbird_discovery import DiscoveryService

            discovery = DiscoveryService(GameService(self.service.store))
            if item.task == "mockingbird_exposure":
                await open_exposure(interaction, discovery, item.identity)
            else:
                await open_discovery(interaction, discovery, item.identity)
        elif item.task == "call_passenger":
            from girlframe.discord_adapter.m3_passengers import open_passenger
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_passengers import PassengerService

            await open_passenger(
                interaction, PassengerService(GameService(self.service.store)), item.identity
            )
        elif item.task == "mockingbird_call":
            from girlframe.discord_adapter.m3_mockingbird_communion import open_call
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_mockingbird_communion import CallService

            await open_call(
                interaction, CallService(GameService(self.service.store)), item.identity
            )
        elif item.task == "mockingbird_sex_revision":
            from girlframe.discord_adapter.m3_mockingbird_revision import open_revision
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_mockingbird_revision import SexRevisionService

            await open_revision(
                interaction, SexRevisionService(GameService(self.service.store)), item.identity
            )
        elif item.task in ("handler_tag_response", "handler_tag_notice"):
            from girlframe.discord_adapter.m3_handler_tags import open_handler_tags
            from girlframe.services.m2_game import GameService

            await open_handler_tags(
                interaction, GameService(self.service.store), identity=item.identity
            )
        elif item.task == "m3_dormant":
            from girlframe.discord_adapter.m3_battle_dormant import open_dormant
            from girlframe.services.m3_battle_dormant import DormantService

            await open_dormant(interaction, DormantService(self.service.store), item.identity)
        elif item.task == "m3_battle_context":
            from girlframe.discord_adapter.m3_battle import open_context as open_battle_context
            from girlframe.services.m3_battle import BattleService

            await open_battle_context(interaction, BattleService(self.service.store), item.identity)
        elif item.task == "m3_handler_notice":
            from girlframe.discord_adapter.m3_handler_plays import open_notice
            from girlframe.services.m3_handler_plays import HandlerPlayService

            await open_notice(interaction, HandlerPlayService(self.service.store), item.identity)
        elif item.task == "m3_handler_play":
            from girlframe.discord_adapter.m3_handler_plays import open_play as open_handler_play
            from girlframe.services.m3_handler_plays import HandlerPlayService

            await open_handler_play(
                interaction, HandlerPlayService(self.service.store), item.identity
            )
        elif item.task == "handler_creation":
            from girlframe.discord_adapter.m3_handler_creation import open_handler
            from girlframe.services.m3_handler_creation import HandlerCreationService

            await open_handler(interaction, HandlerCreationService(self.service.store))
        elif item.task == "handler_creation_npc_agreement":
            from girlframe.discord_adapter.m3_handler_creation import open_npc_agreement
            from girlframe.services.m3_handler_creation import HandlerCreationService

            await open_npc_agreement(
                interaction, HandlerCreationService(self.service.store), item.identity
            )
        elif item.task == "handler_creation_agreement":
            from girlframe.discord_adapter.m3_handler_creation import open_agreement
            from girlframe.services.m3_handler_creation import HandlerCreationService

            await open_agreement(
                interaction, HandlerCreationService(self.service.store), item.identity
            )
        elif item.task == "m3_scene_requisition":
            from girlframe.discord_adapter.m3_scene_requisitions import open_scene
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_scene_requisitions import SceneRequisitionService

            await open_scene(
                interaction, SceneRequisitionService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_privacy_trouble":
            from girlframe.discord_adapter.m3_privacy_trouble import open_trouble
            from girlframe.services.m3_privacy_trouble import PrivacyTroubleService

            await open_trouble(
                interaction, PrivacyTroubleService(self.service.store), item.identity
            )
        elif item.task == "m3_role_punishment":
            from girlframe.discord_adapter.m3_role_punishments import open_role_punishment
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_role_punishments import RolePunishmentService

            await open_role_punishment(
                interaction, RolePunishmentService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_handler_consequence":
            from girlframe.discord_adapter.m3_handler_consequences import open_consequence
            from girlframe.services.m3_handler_consequences import HandlerConsequenceService

            await open_consequence(
                interaction, HandlerConsequenceService(self.service.store), item.identity
            )
        elif item.task == "m3_void":
            from girlframe.discord_adapter.m3_void import open_void
            from girlframe.services.m3_void import VoidService

            await open_void(interaction, VoidService(self.service.store), item.identity)
        elif item.task == "m3_lobotomy":
            from girlframe.discord_adapter.m3_lobotomy import open_lobotomy
            from girlframe.services.m3_lobotomy import LobotomyService

            await open_lobotomy(interaction, LobotomyService(self.service.store), item.identity)
        elif item.task == "m3_frame_swap":
            from girlframe.discord_adapter.m3_frame_swap import open_plan
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_frame_swap import FrameSwapService

            await open_plan(
                interaction, FrameSwapService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_firearm_return":
            from girlframe.discord_adapter.m3_personal_firearm import (
                open_return as open_firearm_return,
            )
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_personal_firearm import PersonalFirearmService

            await open_firearm_return(
                interaction, PersonalFirearmService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_enforcer_volunteer":
            from girlframe.discord_adapter.m3_enforcer_volunteer import open_volunteer_offer
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_enforcer_volunteer import VolunteerService

            await open_volunteer_offer(
                interaction, VolunteerService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_item_fact":
            from girlframe.discord_adapter.m3_items import open_item_fact
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_items import ItemService

            await open_item_fact(
                interaction, ItemService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_enforcer_grasp":
            from girlframe.discord_adapter.m3_enforcement_initiative import open_grasp
            from girlframe.services.m2_game import GameService

            await open_grasp(interaction, GameService(self.service.store), item.identity)
        elif item.task == "m3_enforcer":
            from girlframe.discord_adapter.m3_enforcer import open_enforcer_task
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_enforcer import EnforcerService

            await open_enforcer_task(
                interaction, EnforcerService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_medical":
            from girlframe.discord_adapter.m3_medical import open_medical
            from girlframe.services.m3_medical import MedicalService

            await open_medical(interaction, MedicalService(self.service.store), item.identity)
        elif item.task == "m3_girl_transition":
            from girlframe.discord_adapter.m3_girl_transition import open_transition
            from girlframe.services.m3_girl_transition import GirlTransitionService

            await open_transition(
                interaction, GirlTransitionService(self.service.store), item.identity
            )
        elif item.task == "m3_standards":
            from girlframe.discord_adapter.m3_standards import open_setup
            from girlframe.services.m3_standards import StandardsService

            await open_setup(interaction, StandardsService(self.service.store), item.identity)
        elif item.task == "m3_career":
            from girlframe.discord_adapter.m3_careers import open_archive
            from girlframe.services.m3_careers import CareerService

            await open_archive(interaction, CareerService(self.service.store), item.identity)
        elif item.task == "m3_career_status":
            from girlframe.discord_adapter.m3_careers import open_status
            from girlframe.services.m3_careers import CareerService

            assert item.target is not None
            await open_status(
                interaction, CareerService(self.service.store), item.target, item.identity
            )
        elif item.task == "m3_career_return_offer":
            from girlframe.discord_adapter.m3_careers import open_return_offer
            from girlframe.services.m3_careers import CareerService

            await open_return_offer(interaction, CareerService(self.service.store), item.identity)
        elif item.task == "m3_career_return":
            from girlframe.discord_adapter.m3_careers import open_return
            from girlframe.services.m3_careers import CareerService

            await open_return(interaction, CareerService(self.service.store), item.identity)
        elif item.task == "m3_frame_physical":
            from girlframe.discord_adapter.m3_physical import open_frame
            from girlframe.services.m3_physical import PhysicalService

            await open_frame(interaction, PhysicalService(self.service.store), item.identity)
        elif item.task == "m3_defeat":
            from girlframe.discord_adapter.m3_defeat import open_work as open_defeat_work
            from girlframe.services.m2_game import GameService

            await open_defeat_work(interaction, GameService(self.service.store), item.identity)
        elif item.task == "m3_discipline":
            from girlframe.discord_adapter.m3_punishments import open_discipline
            from girlframe.services.m3_punishments import PunishmentService

            await open_discipline(interaction, PunishmentService(self.service.store), item.identity)
        elif item.task == "m3_mission":
            from girlframe.discord_adapter.m3_missions import open_mission
            from girlframe.services.m3_missions import MissionService

            await open_mission(interaction, MissionService(self.service.store), item.identity)
        elif item.task == "m3_comforts":
            from girlframe.discord_adapter.m3_comforts import open_comfort
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_comforts import ComfortService

            await open_comfort(
                interaction, ComfortService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_physical_start":
            from girlframe.discord_adapter.m3_physical import open_initial
            from girlframe.services.m3_physical import PhysicalService

            await open_initial(interaction, PhysicalService(self.service.store))
        elif item.task == "m3_physical":
            from girlframe.discord_adapter.m3_physical import open_review as open_physical_review
            from girlframe.services.m3_physical import PhysicalService

            await open_physical_review(
                interaction, PhysicalService(self.service.store), item.identity
            )
        elif item.task == "m3_privilege":
            from girlframe.discord_adapter.m3_privileges import open_privilege
            from girlframe.services.m3_privileges import PrivilegeService

            await open_privilege(interaction, PrivilegeService(self.service.store), item.identity)
        elif item.task == "m3_tag_permission":
            from girlframe.discord_adapter.m3_tag_permissions import open_permission
            from girlframe.services.m3_tag_permissions import PermissionService

            await open_permission(interaction, PermissionService(self.service.store), item.identity)
        elif item.task == "m3_contraband":
            from girlframe.discord_adapter.m3_contraband import open_find
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_contraband import ContrabandService

            await open_find(
                interaction, ContrabandService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_shared_recovery":
            from girlframe.discord_adapter.m3_recovery import open_recovery as open_shared_recovery
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_recovery import RecoveryService

            game = GameService(self.service.store)
            saved = await asyncio.to_thread(RecoveryService(game).saved, viewer)
            record = next((x for x in saved if x["id"] == item.identity), None)
            if record is None:
                raise WorkflowError("Refresh your actual saved Play recovery.")
            await open_shared_recovery(interaction, game, record)
        elif item.task == "m3_actor_recovery":
            from girlframe.discord_adapter.m3_actor_plays import open_recovery
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_actor_plays import ActorPlayService

            game = GameService(self.service.store)
            saved = await asyncio.to_thread(ActorPlayService(game).saved, viewer)
            record = next((x for x in saved if x["id"] == item.identity), None)
            if record is None:
                raise WorkflowError("Refresh your actual saved Play recovery.")
            await open_recovery(interaction, game, record)
        elif item.task == "m3_actor_rejection":
            from girlframe.discord_adapter.m3_actor_plays import open_actor_play
            from girlframe.engine.m3_actor_state import ActorRef
            from girlframe.services.m2_game import GameService

            game = GameService(self.service.store)
            owed = await asyncio.to_thread(game.own_obligations, viewer)
            record = next((x for x in owed if x["id"] == item.identity), None)
            if record is None:
                raise WorkflowError("Refresh your actual owned Tag action.")
            await open_actor_play(
                interaction, game, ActorRef.model_validate_json(record["details"]["actor"])
            )
        elif item.task == "m2_choice":
            from girlframe.discord_adapter.m2_ui import open_choice
            from girlframe.services.m2_game import GameService

            await open_choice(interaction, GameService(self.service.store), item.identity)
        elif item.task == "court":
            await open_child(
                "Choose another joined Girl, then review the external AM role.",
                CourtRecipient(self.service, self.owner, item, self),
            )
        elif item.task == "mentor_start" and item.target is not None:
            from girlframe.discord_adapter.bonds import ProposalView

            prepared = await asyncio.to_thread(self.service.bonds.prepare, viewer, item.target)
            await open_child(
                "Review the starting Bond with the Handler-nominated Mentor.",
                ProposalView(self.service.bonds, self.owner, item.target, prepared),
            )
        elif item.task == "callsign" and item.target is not None:
            from girlframe.discord_adapter.shared_setup import ChoiceView

            prepared = await asyncio.to_thread(
                self.service.shared.prepare, viewer, item.target, "callsign"
            )
            name_view = ChoiceView(
                self.service.shared, self.owner, item.target, "callsign", prepared
            )
            await open_child(name_view.text(), name_view)
        elif item.task == "pair" and item.target is not None:
            from girlframe.discord_adapter.pair_assets import PairView
            from girlframe.services.pair_assets import PairService

            pair_service = PairService(self.service.store)
            prepared = await asyncio.to_thread(pair_service.resolve, viewer, item.target)
            pair_view = PairView(pair_service, self.owner, prepared)
            await open_child(pair_view.text(), pair_view)
        elif item.task == "coordinate" and item.target is not None:
            from girlframe.discord_adapter.creation_coordination import ChooserView

            role = cast(Role, item.identity.split(":")[1])
            prepared = await asyncio.to_thread(
                self.service.coordination.prepare, viewer, item.target, role
            )
            child = ChooserView(self.service.coordination, self.owner, item.target, role, prepared)
            child.add_item(InboxBackButton(self))
            await child.render(interaction)
        elif item.task in ("describe", "history", "girl_details"):
            from girlframe.discord_adapter.creation import CreationView, summary
            from girlframe.services.creation import CreationService

            creation = CreationService(self.service.store)
            progress = await asyncio.to_thread(creation.get, viewer)
            builder = CreationView(creation, self.owner, progress)
            if item.task == "girl_details":
                from girlframe.discord_adapter.creation_details import DetailsView

                builder.add_item(InboxBackButton(self))
                details = DetailsView(builder)
                details.add_item(InboxBackButton(self))
                await details.render(interaction)
                return
            if item.task == "history":
                from girlframe.discord_adapter.cadre_history import HistoryView

                cadre = await asyncio.to_thread(creation.cadre, viewer)
                builder.add_item(InboxBackButton(self))
                history = HistoryView(builder, cadre)
                history.add_item(InboxBackButton(self))
                await history.render(interaction)
                return
            await open_child(
                "Use Asset descriptions, then Save progress.\n"
                + summary(progress.draft, progress.pair_choice, progress.shared_choices),
                builder,
            )
        else:
            raise WorkflowError("UNSUPPORTED_RULE: no authorized workflow for this task.")


class InboxBackButton(discord.ui.Button[discord.ui.View]):
    def __init__(self, parent: InboxView):
        super().__init__(label="Back to requests", row=4)
        self.parent_inbox = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        if await self.parent_inbox.interaction_check(interaction):
            self.parent_inbox.overview = True
            self.parent_inbox.focus_key, self.parent_inbox.focus_revision = None, None
            self.parent_inbox.index = (self.parent_inbox.index // 5) * 5
            await interaction.response.defer()
            await self.parent_inbox.present(interaction)


class RecipientSelect(discord.ui.UserSelect["CourtRecipient"]):
    def __init__(self, parent: "CourtRecipient"):
        self.parent_view = parent
        super().__init__(placeholder="Choose another campaign Girl")

    async def callback(self, interaction: discord.Interaction) -> None:
        parent = self.parent_view
        await interaction.response.defer()
        try:
            from girlframe.discord_adapter.shared_setup import ChoiceView

            viewer = viewer_from_interaction(interaction)
            await asyncio.to_thread(
                parent.service.current, viewer, parent.item.key, parent.item.revision
            )
            target = self.values[0].id
            prepared = await asyncio.to_thread(
                parent.service.shared.prepare, viewer, target, "court"
            )
            view = ChoiceView(parent.service.shared, parent.owner, target, "court", prepared)
            if parent.parent_inbox is not None:
                view.add_item(InboxBackButton(parent.parent_inbox))
            await reply(interaction, view.text(), view)
        except WorkflowError as error:
            await reply(interaction, str(error), parent)


class CourtRecipient(discord.ui.View):
    def __init__(
        self, service: InboxService, owner: int, item: InboxItem, parent: InboxView | None = None
    ):
        super().__init__(timeout=600)
        self.service, self.owner, self.item = service, owner, item
        self.parent_inbox = parent
        self.add_item(RecipientSelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "This task belongs to another player.")
            return False
        try:
            await asyncio.to_thread(
                self.service.current,
                viewer_from_interaction(interaction),
                self.item.key,
                self.item.revision,
            )
            return True
        except WorkflowError as error:
            await reply(interaction, str(error))
            return False

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]
    ) -> None:
        await reply(interaction, "Recipient selector unavailable. Reopen /character requests.")
