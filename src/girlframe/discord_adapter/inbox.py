"""Private overview and guided request review. Mutations stay in existing services."""

import asyncio
import hashlib
import re
from dataclasses import replace
from typing import Any, cast
from uuid import uuid4

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.creation import clean
from girlframe.discord_adapter.member_names import member_label, render_member_labels
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
    "facilitator": "Human adjudication",
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
            if item.state == "pending" and not item.incoming and not item.task:
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

        async def named(item: InboxItem) -> InboxItem:
            # This is the existing system-authored counterpart label, not the
            # request's narrative, IDs, source proof or decision ownership.
            match = re.fullmatch(r".+ \(([0-9]{15,20})\)", item.counterpart)
            if match is None:
                return item
            label = await render_member_labels(
                interaction, member_label(match.group(1)), markdown=False
            )
            return replace(item, counterpart=label)

        self.page = replace(
            self.page,
            item=await named(self.page.item) if self.page.item else None,
            window=tuple([await named(item) for item in self.page.window]),
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
        elif item.task == "m3_ancillary_invitation":
            from girlframe.discord_adapter.m3_ancillary import open_invitation as open_ancillary
            from girlframe.services.m3_ancillary import AncillaryService
            from girlframe.services.m3_missions import MissionService

            await open_ancillary(
                interaction, AncillaryService(MissionService(self.service.store)), item.identity
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
        elif item.task == "m3_am_neural_route":
            from girlframe.discord_adapter.m3_am_neural_route import open_neural_route
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_am_neural_route import RouteService

            await open_neural_route(
                interaction, RouteService(GameService(self.service.store)), item.identity
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
        elif item.task == "m3_am_records_source":
            from girlframe.discord_adapter.m3_am_records import open_records_source
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_am_records import RecordsService

            await open_records_source(
                interaction, RecordsService(GameService(self.service.store)), item.identity
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
        elif item.task == "m3_mentor":
            from girlframe.discord_adapter.m3_mentor import open_mentor
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_mentor import MentorService

            await open_mentor(
                interaction, MentorService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_trainee":
            from girlframe.discord_adapter.m3_trainee import open_trainee
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_trainee import TraineeService

            await open_trainee(
                interaction, TraineeService(GameService(self.service.store)), item.identity
            )
        elif item.task in ("m3_show_dog", "m3_show_dog_message", "m3_show_dog_interest"):
            from girlframe.discord_adapter.m3_show_dog import (
                open_interest,
                open_message,
                open_show_dog,
            )
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_show_dog import ShowDogService

            show_dog_operation = (
                open_message
                if item.task == "m3_show_dog_message"
                else open_interest
                if item.task == "m3_show_dog_interest"
                else open_show_dog
            )
            await show_dog_operation(
                interaction, ShowDogService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_vatgrown_doll":
            from girlframe.discord_adapter.m3_vatgrown import open_vatgrown
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_vatgrown import DollService

            await open_vatgrown(
                interaction, DollService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_oldgen_sex":
            from girlframe.discord_adapter.m3_oldgen_sex import open_oldgen_sex
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_oldgen_sex import OldgenSexService

            await open_oldgen_sex(
                interaction, OldgenSexService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_ankou":
            from girlframe.discord_adapter.m3_ankou import open_ankou
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_ankou import AnkouService

            await open_ankou(
                interaction, AnkouService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_casualty_replacement":
            from girlframe.discord_adapter.m3_casualty_replacement import (
                open_replacement as open_casualty_replacement,
            )
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_casualty_replacement import (
                ReplacementService as CasualtyReplacementService,
            )

            await open_casualty_replacement(
                interaction,
                CasualtyReplacementService(GameService(self.service.store)),
                item.identity,
            )
        elif item.task == "m3_gorgon_contact_report":
            from girlframe.discord_adapter.m3_gorgon_contact_disclosure import open_report
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_gorgon_contact_disclosure import (
                FrameContactDisclosureService,
            )

            await open_report(
                interaction,
                FrameContactDisclosureService(GameService(self.service.store)),
                item.identity,
            )
        elif item.task == "m3_harpy_bond_void":
            from girlframe.discord_adapter.m3_harpy_bond_void import open_temptation
            from girlframe.services.m2_game import GameService

            await open_temptation(interaction, GameService(self.service.store), item.identity)
        elif item.task == "m3_npc_flirt":
            from girlframe.discord_adapter.m3_npc_flirt import open_npc_flirt
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_npc_flirt import NpcFlirtService

            await open_npc_flirt(
                interaction, NpcFlirtService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_bonded_rejection":
            from girlframe.discord_adapter.m3_bonded_rejection import open_bonded_rejection
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_bonded_rejection import BondedRejectionService

            await open_bonded_rejection(
                interaction,
                BondedRejectionService(GameService(self.service.store)),
                identity=item.identity,
            )
        elif item.task == "m3_bonded_am":
            from girlframe.discord_adapter.m3_bonded_am import open_bonded_am
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_bonded_am import BondedAMService

            await open_bonded_am(
                interaction,
                BondedAMService(GameService(self.service.store)),
                identity=item.identity,
            )
        elif item.task == "m3_vatgrown_dna":
            from girlframe.discord_adapter.m3_vatgrown_dna import open_vatgrown_dna
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_vatgrown_dna import VatgrownDNAService

            await open_vatgrown_dna(
                interaction, VatgrownDNAService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_body_facts":
            from girlframe.discord_adapter.m3_body_facts import open_body_facts
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_body_facts import BodyFactsService

            await open_body_facts(
                interaction, BodyFactsService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_changeling_sex":
            from girlframe.discord_adapter.m3_changeling_sex import open_changeling_sex
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_changeling_sex import ChangelingSexService

            await open_changeling_sex(
                interaction, ChangelingSexService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_changeling":
            from girlframe.discord_adapter.m3_changeling import open_changeling
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_changeling import ChangelingService

            await open_changeling(
                interaction, ChangelingService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_red_queen":
            from girlframe.discord_adapter.m3_red_queen import open_red_queen
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_red_queen import RedQueenService

            await open_red_queen(
                interaction, RedQueenService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_wyvern_combat":
            from girlframe.discord_adapter.m3_wyvern_combat import open_combat
            from girlframe.services.m2_game import GameService

            await open_combat(interaction, GameService(self.service.store), item.identity)
        elif item.task in ("m3_prince", "m3_consume", "m3_bonded", "m3_wyvern"):
            if item.task == "m3_wyvern":
                from girlframe.discord_adapter.m3_wyvern import open_wyvern
                from girlframe.services.m2_game import GameService
                from girlframe.services.m3_wyvern import WyvernService

                await open_wyvern(
                    interaction, WyvernService(GameService(self.service.store)), item.identity
                )
                return
            elif item.task == "m3_bonded":
                from girlframe.discord_adapter.m3_bonded import open_bonded
                from girlframe.services.m2_game import GameService
                from girlframe.services.m3_bonded import BondedService

                await open_bonded(
                    interaction, BondedService(GameService(self.service.store)), item.identity
                )
                return
            from girlframe.services.m2_game import GameService

            if item.task == "m3_prince":
                from girlframe.discord_adapter.m3_prince import open_prince
                from girlframe.services.m3_prince import PrinceService

                await open_prince(
                    interaction, PrinceService(GameService(self.service.store)), item.identity
                )
            else:
                from girlframe.discord_adapter.m3_consume import open_consume
                from girlframe.services.m3_consume import ConsumeService

                await open_consume(
                    interaction, ConsumeService(GameService(self.service.store)), item.identity
                )
        elif item.task == "p1_facilitator":
            from girlframe.discord_adapter.p1_facilitator import (
                open_request as open_facilitator_request,
            )
            from girlframe.services.m2_game import GameService

            await open_facilitator_request(
                interaction, GameService(self.service.store), item.identity
            )
        elif item.task == "m3_casualty":
            from girlframe.discord_adapter.m3_casualty import open_casualty
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_casualty import CasualtyService

            await open_casualty(
                interaction, CasualtyService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_vatgrown_death":
            from girlframe.discord_adapter.m3_vatgrown_death import open_vatgrown_death
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_vatgrown_death import VatgrownDeathService

            await open_vatgrown_death(
                interaction, VatgrownDeathService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_vatgrown_travel":
            from girlframe.discord_adapter.m3_vatgrown_travel import open_vatgrown_travel
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_vatgrown_travel import VatgrownTravelService

            await open_vatgrown_travel(
                interaction, VatgrownTravelService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_fuel_shortage":
            from girlframe.discord_adapter.m3_fuel_shortage import open_fuel_shortage
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_fuel_shortage import FuelService

            await open_fuel_shortage(
                interaction, FuelService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_prisoner_escape":
            from girlframe.discord_adapter.m3_prisoner_escape import open_prisoner_escape
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_prisoner_escape import PrisonerEscapeService
            from girlframe.services.m3_strain import StrainService

            await open_prisoner_escape(
                interaction,
                PrisonerEscapeService(
                    StrainService(OffDutyService(MissionService(self.service.store)))
                ),
                item.identity,
            )
        elif item.task == "m3_void_frame_entry":
            from girlframe.discord_adapter.m3_void_frame_entry import open_void_frame_entry
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_strain import StrainService
            from girlframe.services.m3_void_frame_entry import VoidFrameEntryService

            await open_void_frame_entry(
                interaction,
                VoidFrameEntryService(
                    StrainService(OffDutyService(MissionService(self.service.store)))
                ),
                item.identity,
            )
        elif item.task == "m3_vatgrown_plays":
            from girlframe.discord_adapter.m3_vatgrown_plays import open_vatgrown_plays
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_vatgrown_plays import VatgrownPlaysService

            await open_vatgrown_plays(
                interaction, VatgrownPlaysService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_newgirl_sex":
            from girlframe.discord_adapter.m3_newgirl_sex import open_newgirl_sex
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_newgirl_sex import NewgirlSexService

            await open_newgirl_sex(
                interaction, NewgirlSexService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_easy_target":
            from girlframe.discord_adapter.m3_easy_target import open_easy_target
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_easy_target import EasyTargetService

            await open_easy_target(
                interaction, EasyTargetService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_oldgen":
            from girlframe.discord_adapter.m3_oldgen import open_oldgen
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_oldgen import OldgenService

            await open_oldgen(
                interaction, OldgenService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_malleable":
            from girlframe.discord_adapter.m3_malleable import open_malleable
            from girlframe.services.m3_malleable import MalleableService

            await open_malleable(interaction, MalleableService(self.service.store), item.identity)
        elif item.task == "m3_native_am":
            from girlframe.discord_adapter.m3_am_sex import open_native
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_am_sex import SexService as AMSexService

            await open_native(
                interaction, AMSexService(GameService(self.service.store)), identity=item.identity
            )
        elif item.task == "m3_learned_am":
            from girlframe.discord_adapter.m3_am_sex import open_am_sex
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_am_sex import SexService as AMSexService

            await open_am_sex(
                interaction, AMSexService(GameService(self.service.store)), identity=item.identity
            )
        elif item.task == "m3_learned_sex":
            from girlframe.discord_adapter.m3_learned_sex import open_learned_sex
            from girlframe.services.m2_game import GameService

            await open_learned_sex(interaction, GameService(self.service.store), item.identity)
        elif item.task == "m3_patrol_harpy":
            from girlframe.discord_adapter.m3_patrol_harpy import open_patrol_harpy
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_patrol_harpy import PatrolHarpyService
            from girlframe.services.m3_strain import StrainService

            source = PatrolHarpyService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            await open_patrol_harpy(interaction, source, item.identity)
        elif item.task == "m3_stim_sex":
            from girlframe.discord_adapter.m3_stim_sex import open_stim
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_stim_sex import SexService as StimSexService

            await open_stim(
                interaction, StimSexService(GameService(self.service.store)), item.identity
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
        elif item.task == "m3_harpy_followthrough":
            from girlframe.discord_adapter.m3_harpy_flirt import open_followthrough
            from girlframe.services.m2_game import GameService

            game = GameService(self.service.store)
            owed = await asyncio.to_thread(
                game.own_obligations, viewer_from_interaction(interaction)
            )
            obligation = next((x for x in owed if x["id"] == item.identity), None)
            if obligation is None:
                raise WorkflowError("This actual follow-through is no longer pending")
            await open_followthrough(interaction, game, obligation)
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
        elif item.task in ("m3_void_leave", "m3_void_leave_poll"):
            from girlframe.discord_adapter.m3_void_leave import open_leave, open_poll
            from girlframe.services.m3_void_leave import LeaveService

            leave_service = LeaveService(self.service.store)
            if item.task == "m3_void_leave":
                await open_leave(interaction, leave_service, item.identity)
            else:
                await open_poll(interaction, leave_service, item.identity)
        elif item.task == "m3_void_lab_portal":
            from girlframe.discord_adapter.m3_void_lab_portal import open_lab
            from girlframe.services.m3_void_lab_portal import LabPortalService

            await open_lab(interaction, LabPortalService(self.service.store), item.identity)
        elif item.task == "m3_handler_retirement":
            from girlframe.discord_adapter.m3_handler_retirement import open_retirement
            from girlframe.services.m3_handler_retirement import RetirementService

            await open_retirement(interaction, RetirementService(self.service.store), item.identity)
        elif item.task == "m3_void_retirement":
            from girlframe.discord_adapter.m3_void_retirement import open_offer
            from girlframe.services.m3_void_retirement import StipendService

            await open_offer(interaction, StipendService(self.service.store), item.identity)
        elif item.task == "m3_director_strain_call":
            from girlframe.discord_adapter.m3_director_strain import open_phone_receipt
            from girlframe.services.m3_director_strain import DirectorStrainService
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_strain import StrainService

            phone_strain = StrainService(OffDutyService(MissionService(self.service.store)))
            await open_phone_receipt(
                interaction, DirectorStrainService(phone_strain), item.identity
            )
        elif item.task == "m3_named_strain":
            from girlframe.discord_adapter.m3_named_strain import open_named_strain
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_named_strain import NamedStrainService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_strain import StrainService

            named_strain = StrainService(OffDutyService(MissionService(self.service.store)))
            await open_named_strain(interaction, NamedStrainService(named_strain), item.identity)
        elif item.task in ("m3_void_privacy_grant", "m3_void_privacy_notice"):
            from girlframe.discord_adapter.m3_void_privacy import open_concealment, open_void_notice
            from girlframe.services.m3_void_privacy import ConcealmentService

            concealment_service = ConcealmentService(self.service.store)
            if item.task == "m3_void_privacy_grant":
                await open_concealment(interaction, concealment_service, item.identity)
            else:
                await open_void_notice(interaction, concealment_service, item.identity)
        elif item.task == "m3_rebel_leader":
            from girlframe.discord_adapter.m3_rebel_leader import open_leader
            from girlframe.services.m3_rebel_leader import LeaderService

            await open_leader(interaction, LeaderService(self.service.store), item.identity)
        elif item.task == "m3_rebel_merge":
            from girlframe.discord_adapter.m3_rebel_merge import open_merger
            from girlframe.services.m3_rebel_merge import MergerService

            await open_merger(interaction, MergerService(self.service.store), item.identity)
        elif item.task == "m3_rebel_takeover":
            from girlframe.discord_adapter.m3_rebel_takeover import open_takeover
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_rebel_takeover import TakeoverService
            from girlframe.services.m3_strain import StrainService

            takeover_service = TakeoverService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            await open_takeover(interaction, takeover_service, item.identity)
        elif item.task == "m3_rebel_succession":
            from girlframe.discord_adapter.m3_rebel_succession import open_succession
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_rebel_succession import SuccessionService
            from girlframe.services.m3_strain import StrainService

            succession_service = SuccessionService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            await open_succession(interaction, succession_service, item.identity)
        elif item.task == "m3_rebel_funding":
            from girlframe.discord_adapter.m3_rebel_funding import open_participation
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_rebel_funding import FundingService
            from girlframe.services.m3_strain import StrainService

            funding_service = FundingService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            await open_participation(interaction, funding_service, item.identity)
        elif item.task == "m3_rebel_assimilation":
            from girlframe.discord_adapter.m3_rebel_assimilation import open_employment
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_rebel_assimilation import AssimilationService
            from girlframe.services.m3_strain import StrainService

            assimilation_service = AssimilationService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            await open_employment(interaction, assimilation_service, item.identity)
        elif item.task == "m3_budget_demotion":
            from girlframe.discord_adapter.m3_budget_demotion import open_demotion
            from girlframe.services.m3_budget_demotion import DemotionService
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_strain import StrainService

            demotion_service = DemotionService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            await open_demotion(interaction, demotion_service, item.identity)
        elif item.task == "m3_budget_trial":
            from girlframe.discord_adapter.m3_budget_trial import open_trial
            from girlframe.services.m3_budget_trial import TrialService
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_strain import StrainService

            trial_service = TrialService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            await open_trial(interaction, trial_service, item.identity)
        elif item.task == "m3_budget_ruin":
            from girlframe.discord_adapter.m3_budget_ruin import open_ruin
            from girlframe.services.m3_budget_ruin import RuinService

            await open_ruin(interaction, RuinService(self.service.store), item.identity)
        elif item.task == "m3_budget_tag":
            from girlframe.discord_adapter.m3_budget_tags import open_gift
            from girlframe.services.m3_budget_tags import BudgetTagService

            await open_gift(interaction, BudgetTagService(self.service.store), item.identity)
        elif item.task == "m3_void_spread_gain":
            from girlframe.discord_adapter.m3_void_spread import open_gain
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_strain import StrainService
            from girlframe.services.m3_void_spread import SpreadService

            spread_service = SpreadService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            await open_gain(interaction, spread_service, item.identity)
        elif item.task == "m3_strain_void_exam":
            from girlframe.discord_adapter.m3_void_examination import open_exam
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_void_examination import ExaminationService

            await open_exam(
                interaction,
                ExaminationService(OffDutyService(MissionService(self.service.store))),
                item.identity,
            )
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
        elif item.task == "m3_insurgent_cover":
            from girlframe.discord_adapter.m3_insurgent_cover import open_cover
            from girlframe.services.m3_insurgent_cover import CoverService
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService

            await open_cover(
                interaction,
                CoverService(OffDutyService(MissionService(self.service.store))),
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
        elif item.task == "m3_handler_recovery":
            from girlframe.discord_adapter.m3_handler_recovery import open_handler_recovery
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_handler_recovery import HandlerRecoveryService

            await open_handler_recovery(
                interaction, HandlerRecoveryService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_doctor_return":
            from girlframe.discord_adapter.m3_doctor_return import open_return as open_doctor_return
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_doctor_return import ReturnService

            await open_doctor_return(
                interaction, ReturnService(GameService(self.service.store)), item.identity
            )
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
        elif item.task == "m3_harpy_creation":
            from girlframe.discord_adapter.m3_harpy_creation import (
                open_creation as open_harpy_creation,
            )
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_harpy_creation import HarpyCreationService

            await open_harpy_creation(
                interaction, HarpyCreationService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_harpy_advancement":
            from girlframe.discord_adapter.m3_harpy_advancements import (
                open_advancement as open_harpy_advancement,
            )
            from girlframe.services.m3_harpy_advancements import HarpyAdvancementService

            await open_harpy_advancement(
                interaction, HarpyAdvancementService(self.service.store), item.identity
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
        elif item.task in ("m3_cadre_leak", "m3_cadre_report", "m3_cadre_apology"):
            from girlframe.discord_adapter.m3_cadre_leak import open_leak
            from girlframe.services.m3_cadre_leak import LeakService
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_strain import StrainService

            leak_service = LeakService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            if item.task in ("m3_cadre_report", "m3_cadre_apology"):
                statement = await asyncio.to_thread(
                    leak_service.bulletin,
                    viewer,
                    item.identity,
                    apology=item.task == "m3_cadre_apology",
                )
                await reply(interaction, discord.utils.escape_mentions(statement))
            else:
                await open_leak(interaction, leak_service, item.identity)
        elif item.task == "m3_harpy_raid":
            from girlframe.discord_adapter.m3_harpy_raid import open_raid
            from girlframe.services.m3_harpy_raid import RaidService
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_strain import StrainService

            raid_service = RaidService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            await open_raid(interaction, raid_service, item.identity)
        elif item.task == "m3_pilot_fears":
            from girlframe.discord_adapter.m3_pilot_fears import open_fears
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_pilot_fears import FearsService
            from girlframe.services.m3_strain import StrainService

            fears_service = FearsService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            await open_fears(interaction, fears_service, item.identity)
        elif item.task == "m3_strain_void_signal":
            from girlframe.discord_adapter.m3_void_signal import open_signal
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_strain import StrainService
            from girlframe.services.m3_void_signal import SignalService

            signal_service = SignalService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            await open_signal(interaction, signal_service, item.identity)
        elif item.task == "m3_civic_directive":
            from girlframe.discord_adapter.m3_civic_directive import open_directive
            from girlframe.services.m3_civic_directive import CivicService
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_strain import StrainService

            civic_service = CivicService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            await open_directive(interaction, civic_service, item.identity)
        elif item.task == "m3_rebel_escape_offer":
            from girlframe.discord_adapter.m3_rebel_escape_offer import (
                open_offer as open_escape_offer,
            )
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_rebel_escape_offer import EscapeOfferService
            from girlframe.services.m3_strain import StrainService

            escape_service = EscapeOfferService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            await open_escape_offer(interaction, escape_service, item.identity)
        elif item.task == "m3_journalist":
            from girlframe.discord_adapter.m3_journalist import open_response
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_journalist import JournalistService

            await open_response(
                interaction, JournalistService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_rebel_taunt":
            from girlframe.discord_adapter.m3_rebel_taunt import open_taunt
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_rebel_taunt import TauntService
            from girlframe.services.m3_strain import StrainService

            taunt_service = TauntService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            await open_taunt(interaction, taunt_service, item.identity)
        elif item.task == "m3_budget_hearing":
            from girlframe.discord_adapter.m3_budget_hearing import open_hearing
            from girlframe.services.m3_budget_hearing import HearingService
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_strain import StrainService

            hearing = HearingService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            await open_hearing(interaction, hearing, item.identity)
        elif item.task == "m3_foundation_attack":
            from girlframe.discord_adapter.m3_foundation_attack import open_attack
            from girlframe.services.m3_foundation_attack import FoundationAttackService
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_strain import StrainService

            foundation_attack_service = FoundationAttackService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            await open_attack(interaction, foundation_attack_service, item.identity)
        elif item.task == "m3_rebel_frame_theft":
            from girlframe.discord_adapter.m3_rebel_frame_theft import open_theft
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_rebel_frame_theft import TheftService
            from girlframe.services.m3_strain import StrainService

            theft_service = TheftService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            await open_theft(interaction, theft_service, item.identity)
        elif item.task == "m3_rebel_bond_attack":
            from girlframe.discord_adapter.m3_rebel_bond_attack import open_betrayal
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_rebel_bond_attack import AttackService
            from girlframe.services.m3_strain import StrainService

            service = AttackService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            await open_betrayal(interaction, service, item.identity)
        elif item.task == "m3_rebel_hunt":
            from girlframe.discord_adapter.m3_rebel_ambush import open_hunt
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_rebel_ambush import HuntService

            await open_hunt(
                interaction, HuntService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_rebel_ambush":
            from girlframe.discord_adapter.m3_rebel_ambush import open_ambush
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_rebel_ambush import AmbushService

            await open_ambush(
                interaction, AmbushService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_berserk_frame":
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_berserk_frame import view as berserk_view

            data = await asyncio.to_thread(
                berserk_view,
                GameService(self.service.store),
                viewer_from_interaction(interaction),
                item.identity,
            )
            detail = (
                "The Aggressive Gorgon was defeated. Any cockpit or medical recovery is separate."
                if data["defeated"]
                else "The original Frame has become an Aggressive Gorgon."
                if data["activated"]
                else "The original Frame's next activation is pending."
            )
            await reply(interaction, detail)
        elif item.task == "m3_bunk_harpy":
            from girlframe.discord_adapter.m3_bunk_harpy import open_bunk
            from girlframe.services.m3_bunk_harpy import BunkService
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_strain import StrainService

            bunk = BunkService(StrainService(OffDutyService(MissionService(self.service.store))))
            await open_bunk(interaction, bunk, item.identity)
        elif item.task == "m3_rebel_voice":
            from girlframe.discord_adapter.m3_rebel_voice import open_voice
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_rebel_voice import VoiceService
            from girlframe.services.m3_strain import StrainService

            voice_service = VoiceService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            await open_voice(interaction, voice_service, item.identity)
        elif item.task == "m3_rebel_strafe":
            from girlframe.discord_adapter.m3_rebel_strafe import open_strafe
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_rebel_strafe import StrafeService
            from girlframe.services.m3_strain import StrainService

            strafe_service = StrafeService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            await open_strafe(interaction, strafe_service, item.identity)
        elif item.task == "m3_npc_interest":
            from girlframe.discord_adapter.m3_npc_interest import open_interest as open_npc_interest
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_npc_interest import InterestService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_strain import StrainService

            interest_service = InterestService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            await open_npc_interest(interaction, interest_service, item.identity)
        elif item.task == "m3_rebel_defection":
            from girlframe.discord_adapter.m3_rebel_defection import open_defection
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_rebel_defection import DefectionService
            from girlframe.services.m3_strain import StrainService

            defection_service = DefectionService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            await open_defection(interaction, defection_service, item.identity)
        elif item.task == "m3_benevolent_contact":
            from girlframe.discord_adapter.m3_benevolent_contact import (
                open_contact as open_gorgon_contact,
            )
            from girlframe.services.m3_benevolent_contact import (
                ContactService as GorgonContactService,
            )
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_strain import StrainService

            gorgon_contact = GorgonContactService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            await open_gorgon_contact(interaction, gorgon_contact, item.identity)
        elif item.task in ("m3_strain_revelation", "m3_strain_disguise_revelation"):
            from girlframe.engine.m3_void_revelation import PLAYS
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_strain import StrainService
            from girlframe.services.m3_strain_effects import EffectService

            effect_service = EffectService(
                StrainService(OffDutyService(MissionService(self.service.store)))
            )
            if item.task == "m3_strain_disguise_revelation":
                value = await asyncio.to_thread(
                    effect_service.disguise_revelation, viewer, item.identity
                )
                title = value["name"] + " · " + value["gorgon_class"].title() + " Dopplegänger"
            else:
                value = await asyncio.to_thread(effect_service.revelation, viewer, item.identity)
                title = next(title for play, title in PLAYS if play == value["play"])
            await reply(interaction, title + "\n" + value["account"])
        elif item.task == "m3_handler_notice":
            from girlframe.discord_adapter.m3_handler_plays import open_notice
            from girlframe.services.m3_handler_plays import HandlerPlayService

            await open_notice(interaction, HandlerPlayService(self.service.store), item.identity)
        elif item.task == "m3_last_resort":
            from girlframe.discord_adapter.m3_last_resort import open_reserve
            from girlframe.services.m3_last_resort import LastResortService

            await open_reserve(interaction, LastResortService(self.service.store), item.identity)
        elif item.task == "m3_successor":
            from girlframe.discord_adapter.m3_successor import open_successor
            from girlframe.services.m3_successor import SuccessorService

            await open_successor(interaction, SuccessorService(self.service.store), item.identity)
        elif item.task == "m3_frantic_crisis":
            from girlframe.discord_adapter.m3_frantic_crisis import open_crisis
            from girlframe.services.m3_frantic_crisis import CrisisService

            await open_crisis(interaction, CrisisService(self.service.store), item.identity)
        elif item.task == "m3_frantic_breakdown":
            from girlframe.discord_adapter.m3_frantic_breakdown import open_breakdown
            from girlframe.services.m3_frantic_breakdown import FranticBreakdownService

            await open_breakdown(
                interaction, FranticBreakdownService(self.service.store), item.identity
            )
        elif item.task == "m3_advocate_alone":
            from girlframe.discord_adapter.m3_advocate_alone import open_response as open_advocate
            from girlframe.services.m3_advocate_alone import AdvocateAloneService

            await open_advocate(
                interaction, AdvocateAloneService(self.service.store), item.identity
            )
        elif item.task == "m3_conditioning":
            from girlframe.discord_adapter.m3_conditioning import open_request as open_conditioning
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_conditioning import ConditioningService

            await open_conditioning(
                interaction, ConditioningService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_mistress_favor":
            from girlframe.discord_adapter.m3_handler_private_scene import open_favor
            from girlframe.services.m3_handler_private_scene import HandlerPrivateSceneService

            await open_favor(
                interaction, HandlerPrivateSceneService(self.service.store), item.identity
            )
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
        elif item.task == "m3_harpy_visions":
            from girlframe.discord_adapter.m3_harpy_visions import open_visions_response
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_harpy_visions import VisionsService

            await open_visions_response(
                interaction,
                VisionsService(GameService(self.service.store)),
                item.identity,
            )
        elif item.task == "m3_harpy_voidspace":
            from girlframe.discord_adapter.m3_harpy_voidspace import open_passage
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_harpy_voidspace import HarpyVoidspaceService

            await open_passage(
                interaction, HarpyVoidspaceService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_harpy_rewrite":
            from girlframe.discord_adapter.m3_harpy_rewrite import open_rewrite_response
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_harpy_rewrite import RewriteService

            await open_rewrite_response(
                interaction, RewriteService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_harpy_mask":
            from girlframe.discord_adapter.m3_harpy_mask import open_mask_response
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_harpy_mask import MaskService

            await open_mask_response(
                interaction, MaskService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_captured":
            from girlframe.discord_adapter.m3_captured import open_capture_choice
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_captured import CapturedService

            await open_capture_choice(
                interaction, CapturedService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_escape":
            from girlframe.discord_adapter.m3_escape import open_escape_choice
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_escape import EscapeService

            await open_escape_choice(
                interaction, EscapeService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_ancillary_private_play":
            from girlframe.discord_adapter.m3_ancillary_intimacy import (
                open_ancillary_intimacy_choice,
            )
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_ancillary_intimacy import AncillaryIntimacyService

            await open_ancillary_intimacy_choice(
                interaction, AncillaryIntimacyService(GameService(self.service.store)),
                item.identity, item.source.removeprefix("ancillary_private_"),
            )
        elif item.task == "m3_chained_placement":
            from girlframe.discord_adapter.m3_chained_darling import open_chained_review
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_chained_darling import ChainedPlacementService

            await open_chained_review(
                interaction, ChainedPlacementService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_chronically_online":
            from girlframe.discord_adapter.m3_chronically_online import open_recollection_inbox
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_chronically_online import ChronicallyOnlineService

            await open_recollection_inbox(
                interaction,
                ChronicallyOnlineService(GameService(self.service.store)),
                item.identity,
            )
        elif item.task == "m3_mercenary_debt":
            from girlframe.discord_adapter.m3_mercenary_debt import open_debt_response
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_mercenary_debt import DebtService

            await open_debt_response(
                interaction, DebtService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_mercenary_patron":
            from girlframe.discord_adapter.m3_mercenary_patron import open_patron_inbox
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_mercenary_patron import MercenaryPatronService

            await open_patron_inbox(
                interaction, MercenaryPatronService(GameService(self.service.store)), item.identity,
                item.source.removeprefix("mercenary_patron_"),
            )
        elif item.task == "m3_harpy_kiss":
            from girlframe.discord_adapter.m3_harpy_kiss import open_surprise
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_harpy_kiss import KissService

            await open_surprise(
                interaction, KissService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_harpy_intimacy":
            from girlframe.discord_adapter.m3_harpy_intimacy import open_intimacy_choice
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_harpy_intimacy import HarpyIntimacyService

            await open_intimacy_choice(
                interaction, HarpyIntimacyService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_abysstech":
            from girlframe.discord_adapter.m3_abysstech import open_abysstech_contact
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_abysstech import AbysstechService

            await open_abysstech_contact(
                interaction, AbysstechService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_warboy_hate":
            from girlframe.discord_adapter.m3_warboy_hate import open_conditioned_hate
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_warboy_hate import ConditionedHateService

            await open_conditioned_hate(
                interaction, ConditionedHateService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_timeskip":
            from girlframe.discord_adapter.m3_timeskip import open_timeskip
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_timeskip import TimeskipService

            await open_timeskip(
                interaction, TimeskipService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_voidspace_invasion":
            from girlframe.discord_adapter.m3_voidspace_invasion import open_invasion
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_voidspace_invasion import InvasionService

            await open_invasion(
                interaction, InvasionService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_npc_handover":
            from girlframe.discord_adapter.m3_npc_handover import open_handover_choice
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_npc_handover import NpcHandoverService

            await open_handover_choice(
                interaction, NpcHandoverService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_npc_intelligence":
            from girlframe.discord_adapter.m3_npc_intelligence import open_inquiry_result
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_npc_intelligence import IntelligenceService

            await open_inquiry_result(
                interaction, IntelligenceService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_harpy_visions_recovery":
            from girlframe.discord_adapter.m3_harpy_visions import open_visions_recovery
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_harpy_visions import VisionsService

            await open_visions_recovery(
                interaction, VisionsService(GameService(self.service.store)), item.identity
            )
        elif item.task == "m3_harpy_gaze":
            from girlframe.discord_adapter.m3_harpy_gaze import open_gaze_response
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_harpy_gaze import GazeService

            await open_gaze_response(
                interaction,
                GazeService(GameService(self.service.store)),
                item.identity,
            )
        elif item.task == "m3_eagle_restore":
            from girlframe.discord_adapter.m3_harpy_eagle import open_restore
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_harpy_eagle import EagleService

            await open_restore(
                interaction,
                EagleService(GameService(self.service.store)),
                item.identity,
                item.revision,
            )
        elif item.task == "m3_harpy_song":
            from girlframe.discord_adapter.m3_harpy_song import open_song_response
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_harpy_song import HarpySongService

            await open_song_response(
                interaction,
                HarpySongService(GameService(self.service.store)),
                item.identity,
            )
        elif item.task == "m3_sniff_out":
            from girlframe.discord_adapter.m3_sniff_out import open_search
            from girlframe.services.m3_sniff_out import SniffOutService

            await open_search(interaction, SniffOutService(self.service.store), item.identity)
        elif item.task == "m3_npc_care":
            from girlframe.discord_adapter.m3_npc_care import open_care as open_npc_care
            from girlframe.services.m3_npc_care import NpcCareService

            await open_npc_care(interaction, NpcCareService(self.service.store), item.identity)
        elif item.task == "m3_parasite_excision":
            from girlframe.discord_adapter.m3_gorgon_runtime import open_excision
            from girlframe.services.m3_parasite_excision import ExcisionService

            await open_excision(interaction, ExcisionService(self.service.store), item.identity)
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
