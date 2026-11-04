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

        if item.task == "m3_off_duty":
            from girlframe.discord_adapter.m3_off_duty import open_period
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService

            await open_period(interaction, OffDutyService(MissionService(self.service.store)))
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
        elif item.task == "m3_reaction":
            from girlframe.discord_adapter.m3_reactions import open_reaction
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_reactions import ReactionService

            await open_reaction(
                interaction, ReactionService(MissionService(self.service.store)), item.identity
            )
        elif item.task == "m3_discipline":
            from girlframe.discord_adapter.m3_punishments import open_discipline
            from girlframe.services.m3_punishments import PunishmentService

            await open_discipline(interaction, PunishmentService(self.service.store), item.identity)
        elif item.task == "m3_mission":
            from girlframe.discord_adapter.m3_missions import open_mission
            from girlframe.services.m3_missions import MissionService

            await open_mission(interaction, MissionService(self.service.store), item.identity)
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
