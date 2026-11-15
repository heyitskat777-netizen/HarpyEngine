"""One private Start/Resume guide over existing saved setup and owned native forms."""

import asyncio
import inspect
from typing import Any

import discord
from discord import app_commands

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.member_names import (
    member_label,
    render_member_labels,
    render_member_view,
)
from girlframe.discord_adapter.onboarding import action_gate, open_draft, reply, sheet_text
from girlframe.services.character_tags import CharacterTagSynchronizer
from girlframe.services.creation import CreationService
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.start_dashboard import StartDashboardService

_LABELS = {
    "join": "Join campaign",
    "profile": "Choose playbooks and callsign",
    "build": "Continue character details",
    "bond": "Choose starting Bond",
    "requests": "Open pending requests",
    "status": "Confirm Status order",
    "creation_rules": "Review starting settings",
    "handler": "Choose Handler",
    "review": "Review and save sheet",
    "activate": "Review activation",
    "ready": "Choose a Play",
    "server": "Set up server channels",
    "create": "Name campaign",
    "court": "Review Court setup",
    "mentor_callsign": "Review Mentor callsign",
    "pair_assets": "Choose Pair Assets",
    "history": "Continue prior missions",
    "girl_setup": "Continue Girl setup",
    "frame_details": "Continue Frame setup",
}
_ICONS = {"complete": "✓", "next": "→", "waiting": "Waiting", "blocked": "Needs attention"}
_EDITORS = {
    "profile",
    "build",
    "review",
    "activate",
    "girl_setup",
    "frame_details",
    "history",
    "bond",
    "court",
    "mentor_callsign",
    "pair_assets",
}


class GuideBack(discord.ui.Button[Any]):
    def __init__(self, controller: "StartController", owner: int, mode: str):
        super().__init__(label="Back to setup guide", row=4)
        self.controller, self.owner, self.mode = controller, owner, mode

    async def callback(self, interaction: discord.Interaction) -> None:
        self.controller.owner(interaction, self.owner)
        await self.controller.show(interaction, self.mode)


class GuideSelect(discord.ui.Select["StartView"]):
    def __init__(self, parent: "StartView", steps: list[dict[str, Any]]):
        self.parent_guide = parent
        self.routes = {x["key"]: x["route"] for x in steps}
        super().__init__(
            placeholder="Review a step or return to an earlier one",
            row=0,
            options=[
                discord.SelectOption(
                    value=x["key"],
                    label=x["label"][:100],
                    description=_ICONS.get(x["status"], "Needs attention"),
                )
                for x in steps[:25]
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        parent = self.parent_guide
        parent.controller.owner(interaction, parent.owner)
        route = self.routes.get(self.values[0])
        if route is None:
            raise WorkflowError("Refresh the guide and choose a current step.")
        await parent.controller.open(interaction, route, parent.mode)


class GuideAction(discord.ui.Button["StartView"]):
    def __init__(self, label: str, action: str, *, row: int, primary: bool = False):
        super().__init__(
            label=label[:80],
            row=row,
            style=discord.ButtonStyle.primary if primary else discord.ButtonStyle.secondary,
        )
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        parent = self.view
        assert isinstance(parent, StartView)
        parent.controller.owner(interaction, parent.owner)
        if self.action in {"home", "character", "campaign"}:
            await parent.controller.show(interaction, self.action)
        elif self.action == "refresh":
            await parent.controller.show(interaction, parent.mode)
        elif self.action == "continue":
            await parent.controller.continue_step(interaction, parent.mode)
        else:
            await parent.controller.open(interaction, self.action, parent.mode)


class StartView(discord.ui.View):
    def __init__(
        self, controller: "StartController", owner: int, mode: str, snapshot: dict[str, Any]
    ):
        super().__init__(timeout=600)
        self.controller, self.owner, self.mode = controller, owner, mode
        if mode == "home":
            self.add_item(
                GuideAction("Create / Resume character", "character", row=0, primary=True)
            )
            if snapshot["is_admin"] or snapshot["is_handler"]:
                self.add_item(GuideAction("Campaign setup", "campaign", row=0))
        else:
            steps = snapshot["character" if mode == "character" else "campaign"]["steps"]
            self.add_item(GuideSelect(self, steps))
            route = (
                snapshot["character"]["next_route"]
                if mode == "character"
                else next((x["route"] for x in steps if x["status"] == "next"), "requests")
            )
            if not snapshot["joined"]:
                route = "join"
            if route != "ready" or snapshot["character"]["release_enabled"]:
                self.add_item(GuideAction("Continue / next step", "continue", row=1, primary=True))
            self.add_item(GuideAction("Back to Start", "home", row=1))
        if not snapshot["joined"]:
            self.add_item(GuideAction("Join campaign", "join", row=2))
        else:
            self.add_item(GuideAction("Pending requests", "requests", row=2))
        if snapshot["character"]["exists"]:
            self.add_item(GuideAction("My sheet", "sheet", row=2))
        if snapshot["activated"] and snapshot["character"]["release_enabled"]:
            self.add_item(GuideAction("Play", "ready", row=2))
        if mode == "campaign" and snapshot["is_handler"]:
            self.add_item(GuideAction("Nominate a Mentor", "mentor", row=2))
        self.add_item(GuideAction("Refresh progress", "refresh", row=3))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        try:
            self.controller.owner(interaction, self.owner)
            return True
        except WorkflowError as error:
            await reply(interaction, str(error))
            return False

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]
    ) -> None:
        notice = (
            str(error)
            if isinstance(error, WorkflowError)
            else "This step is unavailable. Refresh the saved guide before trying again."
        )
        await self.controller.show(interaction, self.mode, notice=notice)


class MemberStep(discord.ui.UserSelect["MemberStepView"]):
    def __init__(self) -> None:
        super().__init__(
            placeholder="Choose the current server member", min_values=1, max_values=1, row=0
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        parent = self.view
        assert isinstance(parent, MemberStepView)
        parent.controller.owner(interaction, parent.owner)
        member = self.values[0]
        if not isinstance(member, discord.Member):
            raise WorkflowError("Choose a current member of this server.")
        await parent.controller.invoke(
            interaction,
            "campaign handler" if parent.route == "handler" else "character bond",
            member=member,
        )


class MemberStepView(discord.ui.View):
    def __init__(self, controller: "StartController", owner: int, route: str, mode: str):
        super().__init__(timeout=600)
        self.controller, self.owner, self.route = controller, owner, route
        self.add_item(MemberStep())
        self.add_item(GuideBack(controller, owner, mode))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "This setup choice belongs to another member.")
            return False
        return True

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]
    ) -> None:
        await reply(
            interaction,
            str(error)
            if isinstance(error, WorkflowError)
            else "Reopen /start to check this saved step.",
            self,
        )


class CampaignName(discord.ui.Modal, title="Name this campaign"):
    name_input: discord.ui.TextInput[discord.ui.Modal] = discord.ui.TextInput(
        label="Campaign name", max_length=80
    )

    def __init__(self, controller: "StartController", owner: int):
        super().__init__(timeout=600)
        self.controller, self.owner = controller, owner

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.controller.owner(interaction, self.owner)
        await self.controller.invoke(interaction, "campaign create", name=str(self.name_input))

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item[Any] | None = None,
    ) -> None:
        await reply(
            interaction,
            str(error)
            if isinstance(error, WorkflowError)
            else "Reopen /start to check campaign setup.",
        )


class MentorMember(discord.ui.UserSelect["MentorGuide"]):
    def __init__(self, role: str, row: int):
        super().__init__(
            placeholder="Choose the Newgirl" if role == "newgirl" else "Choose her Mentor",
            min_values=1,
            max_values=1,
            row=row,
        )
        self.role = role

    async def callback(self, interaction: discord.Interaction) -> None:
        parent = self.view
        assert isinstance(parent, MentorGuide)
        parent.controller.owner(interaction, parent.owner)
        member = self.values[0]
        if not isinstance(member, discord.Member):
            raise WorkflowError("Choose a current member of this server.")
        parent.people[self.role] = member
        parent.confirm.disabled = len(parent.people) != 2
        await interaction.response.defer(ephemeral=True)
        await reply(
            interaction,
            "Newgirl and Mentor are selected. Review the nomination next; "
            "the agreement still needs the actual players' consent.",
            parent,
        )


class MentorGuide(discord.ui.View):
    def __init__(self, controller: "StartController", owner: int):
        super().__init__(timeout=600)
        self.controller, self.owner = controller, owner
        self.people: dict[str, discord.Member] = {}
        self.add_item(MentorMember("newgirl", 0))
        self.add_item(MentorMember("member", 1))
        self.add_item(GuideBack(controller, owner, "campaign"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "This nomination belongs to its Handler.")
            return False
        return True

    @discord.ui.button(
        label="Review nomination", style=discord.ButtonStyle.primary, disabled=True, row=2
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        self.controller.owner(interaction, self.owner)
        if len(self.people) != 2:
            raise WorkflowError("Choose both actual Pilots first.")
        await self.controller.invoke(interaction, "campaign mentor", **self.people)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]
    ) -> None:
        await reply(
            interaction,
            str(error)
            if isinstance(error, WorkflowError)
            else "Reopen /start to review the current nomination.",
            self,
        )


class StartController:
    def __init__(
        self,
        tree: app_commands.CommandTree,
        guild_id: int,
        store: OnboardingStore,
        game: GameService,
        tags: CharacterTagSynchronizer | None = None,
    ):
        self.tree, self.guild_id, self.store, self.game, self.tags = (
            tree,
            guild_id,
            store,
            game,
            tags,
        )
        self.progress = StartDashboardService(store)

    def owner(self, interaction: discord.Interaction, owner: int) -> None:
        self.store.guild_member(viewer_from_interaction(interaction))
        if interaction.user.id != owner:
            raise WorkflowError(
                "This private guide belongs to another member. Open your own /start."
            )

    async def snapshot(self, interaction: discord.Interaction) -> dict[str, Any]:
        return await asyncio.to_thread(self.progress.snapshot, viewer_from_interaction(interaction))

    async def continue_step(self, interaction: discord.Interaction, mode: str) -> None:
        data = await self.snapshot(interaction)
        route = (
            data["character"]["next_route"]
            if mode != "campaign"
            else next(
                (x["route"] for x in data["campaign"]["steps"] if x["status"] == "next"), "requests"
            )
        )
        if not data["joined"]:
            route = "join"
        await self.open(interaction, route, mode)

    async def show(
        self, interaction: discord.Interaction, mode: str = "home", *, notice: str = ""
    ) -> None:
        self.store.guild_member(viewer_from_interaction(interaction))
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)
        data = await self.snapshot(interaction)
        if mode == "campaign" and not (data["is_admin"] or data["is_handler"]):
            mode, notice = (
                "home",
                "Campaign changes belong to the appointed Handler or configured administrators.",
            )
        character = data["character"]
        lines = [
            "**HarpyEngine — Start / Resume**",
            "Confirmed choices are saved. Reopen /start to resume; activation "
            "and other people's consent stay explicit.",
        ]
        if notice:
            lines.append(clean(notice))
        if data["is_handler"]:
            lines.append(
                "Your roles: Handler"
                + (" and Pilot" if character["exists"] else "; you may also create a Pilot")
            )
        if character["exists"]:
            lines.append(
                "Character: "
                + clean(character.get("callsign", ""))
                + (" · activated" if data["activated"] else " · setup in progress")
            )
        if mode in {"campaign", "character"}:
            lines.append(
                "\n**" + ("Campaign setup" if mode == "campaign" else "Character setup") + "**"
            )
            for step in data[mode]["steps"]:
                lines.append(_ICONS.get(step["status"], "Needs attention") + " · " + step["label"])
            next_route = (
                character["next_route"]
                if mode == "character"
                else next(
                    (x["route"] for x in data["campaign"]["steps"] if x["status"] == "next"),
                    "requests",
                )
            )
            lines.append("Next action: " + _LABELS.get(next_route, "Open pending requests"))
        if mode == "character":
            for issue in character["issues"][:3]:
                lines.append(
                    ("Waiting: " if issue["waiting"] else "Next: ") + clean(issue["message"])
                )
            if len(character["issues"]) > 3:
                lines.append("Open the sheet review for the remaining creation requirements.")
        requests = character["requests"]
        lines.append(
            f"\nRequests: {requests['actionable']} need you · "
            f"{requests['waiting']} waiting on someone else"
        )
        if data["campaign"]["handler_id"]:
            lines.append("Handler: " + member_label(data["campaign"]["handler_id"]))
        if data["activated"]:
            lines.append("Creation is complete. Use My sheet, Pending requests or Play.")
        elif character["review_ready"] and not character["release_enabled"]:
            lines.append(
                "Playable activation awaits scoped rules approval; your saved creation is retained."
            )
        lines.append("Safety: /safety pause · /safety resume")
        view = StartView(self, interaction.user.id, mode, data)
        text = await render_member_labels(interaction, "\n".join(lines))
        await render_member_view(interaction, view)
        await interaction.edit_original_response(
            content=text, embed=None, view=view, allowed_mentions=discord.AllowedMentions.none()
        )

    def back(self, view: discord.ui.View, owner: int, mode: str) -> None:
        if not any(isinstance(x, GuideBack) for x in view.children):
            view.add_item(GuideBack(self, owner, mode))

    async def saved(self, interaction: discord.Interaction) -> None:
        notice = interaction.extras.get("guided_save_notice", "Your progress is saved.")
        await self.show(interaction, "character", notice=str(notice))

    async def invoke(self, interaction: discord.Interaction, path: str, **values: Any) -> None:
        parts = path.split()
        command: Any = self.tree.get_command(parts[0], guild=discord.Object(id=self.guild_id))
        for part in parts[1:]:
            if not isinstance(command, app_commands.Group):
                raise WorkflowError("This setup entry point is unavailable.")
            command = command.get_command(part)
        if not isinstance(command, app_commands.Command):
            raise WorkflowError("This setup entry point is unavailable.")
        for check in command.checks:
            result = check(interaction)
            if inspect.isawaitable(result):
                result = await result
            if not result:
                raise WorkflowError("This action is unavailable for your current account.")
        callback: Any = command.callback
        await callback(interaction, **values)

    async def open(
        self, interaction: discord.Interaction, route: str, mode: str = "character"
    ) -> None:
        self.store.guild_member(viewer_from_interaction(interaction))
        data = await self.snapshot(interaction)
        if data["activated"] and route in _EDITORS:
            await self.show(
                interaction,
                "character",
                notice="This character is already activated; its saved creation will not be reset.",
            )
            return
        if route in {"server", "create", "handler"} and not data["is_admin"]:
            await self.show(
                interaction,
                mode,
                notice="A configured server administrator must complete this campaign step.",
            )
            return
        if route in {"status", "creation_rules"} and not data["is_handler"]:
            await self.show(
                interaction,
                mode,
                notice=(
                    "Waiting for the appointed Handler to confirm this step. "
                    "You can continue your own character details."
                ),
            )
            return
        if route == "join":
            if not await action_gate(interaction, "metadata"):
                return
            await asyncio.to_thread(
                self.store.join, viewer_from_interaction(interaction), str(interaction.id)
            )
            await self.show(
                interaction, mode, notice="Joined the campaign. Continue your saved setup."
            )
        elif route == "profile":
            profile_view = await open_draft(
                interaction, self.store, self.tags, autosave=True, on_saved=self.saved
            )
            if profile_view is not None:
                self.back(profile_view, interaction.user.id, mode)
                await interaction.edit_original_response(view=profile_view)
        elif route in {"build", "girl_setup", "frame_details", "history"}:
            from girlframe.discord_adapter.creation import CreationView

            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True, thinking=True)
            service = CreationService(self.store)
            progress = await asyncio.to_thread(service.get, viewer_from_interaction(interaction))
            view = CreationView(
                service, interaction.user.id, progress, autosave=True, on_saved=self.saved
            )
            self.back(view, interaction.user.id, mode)
            await view.render(
                interaction,
                "**Guided creation — confirmed edits save automatically.**\n"
                "Use the section buttons, then Save and continue.\n",
            )
        elif route == "review":
            from girlframe.discord_adapter.creation_review import ReviewView

            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True, thinking=True)
            review = ReviewView(
                CreationReviewService(self.store), interaction.user.id, on_saved=self.saved
            )
            self.back(review, interaction.user.id, mode)
            await review.present(interaction)
        elif route == "activate":
            from girlframe.discord_adapter.m2_ui import open_activation

            form = await open_activation(interaction, self.game)
            if form is not None:
                self.back(form, interaction.user.id, mode)
                await interaction.edit_original_response(view=form)
        elif route in {"handler", "bond"}:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True, thinking=True)
            member_view = MemberStepView(self, interaction.user.id, route, mode)
            await reply(
                interaction,
                "Choose the Handler; the appointment still requires confirmation."
                if route == "handler"
                else (
                    "Choose the other Pilot for your starting Bond. "
                    "Their acceptance remains a separate action."
                ),
                member_view,
            )
        elif route == "mentor":
            if not data["is_handler"]:
                raise WorkflowError("Only the appointed Handler may nominate a Mentor.")
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True, thinking=True)
            await reply(
                interaction,
                "Choose the actual Newgirl and Mentor. The existing nomination review "
                "and player agreement follow.",
                MentorGuide(self, interaction.user.id),
            )
        elif route == "create":
            await interaction.response.send_modal(CampaignName(self, interaction.user.id))
        elif route == "requests":
            from girlframe.discord_adapter.inbox import InboxView
            from girlframe.services.inbox import InboxService

            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True, thinking=True)
            inbox = InboxView(InboxService(self.store), interaction.user.id)
            self.back(inbox, interaction.user.id, mode)
            await inbox.present(interaction)
        elif route == "sheet":
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True, thinking=True)
            if data["activated"]:
                from girlframe.discord_adapter.m2_ui import StatePages

                pages = StatePages(self.game, interaction.user.id)
                self.back(pages, interaction.user.id, mode)
                await pages.show(interaction)
            else:
                draft = await asyncio.to_thread(
                    self.store.draft, viewer_from_interaction(interaction)
                )
                await reply(
                    interaction,
                    sheet_text(draft),
                    StartView(self, interaction.user.id, "home", data),
                )
        elif route in {"court", "mentor_callsign", "pair_assets"}:
            await self.invoke(
                interaction,
                "character " + ("requests" if route != "pair_assets" else "pair_assets"),
            )
        elif route == "ready":
            await self.invoke(interaction, "play")
        elif route in {"server", "status", "creation_rules"}:
            await self.invoke(
                interaction,
                {
                    "server": "server setup",
                    "status": "campaign status_setup",
                    "creation_rules": "campaign creation_rules",
                }[route],
            )
        else:
            raise WorkflowError("Refresh /start to choose an available setup step.")


def register_start(
    tree: app_commands.CommandTree,
    guild_id: int,
    store: OnboardingStore,
    game: GameService,
    tags: CharacterTagSynchronizer | None = None,
) -> StartController:
    controller = StartController(tree, guild_id, store, game, tags)

    @app_commands.command(
        name="start",
        description="Start or resume campaign setup, character creation and pending requests",
    )
    @app_commands.guild_only()
    async def start(interaction: discord.Interaction) -> None:
        if not await action_gate(interaction, "inbox_read"):
            return
        try:
            await controller.show(interaction)
        except WorkflowError as error:
            await reply(interaction, str(error))

    tree.add_command(start, guild=discord.Object(id=guild_id))
    return controller
