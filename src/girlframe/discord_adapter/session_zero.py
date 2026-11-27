"""Private native Discord controls for the group Session Zero worksheet."""

import asyncio
from collections.abc import Callable
from io import BytesIO
from typing import Any

import discord
from discord import app_commands
from pydantic import ValidationError

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.onboarding import action_gate, reply
from girlframe.engine.campaign_opening import (
    DEFAULT_DIFFICULTY,
    DIFFICULTIES,
    DIFFICULTY_DESCRIPTIONS,
)
from girlframe.engine.m3_handler_state import PLAYBOOKS, Playbook
from girlframe.engine.session_zero import (
    CHARACTER_NOTES_LIMIT,
    MAX_GROUP,
    CharacterNotes,
    HandlerProfile,
)
from girlframe.services.onboarding import WorkflowError
from girlframe.services.session_zero import SessionZeroService
from girlframe.services.session_zero_opening import DEFAULT_ROLEPLAY_DAYS


async def open_panel(
    interaction: discord.Interaction, service: SessionZeroService, feedback: str = ""
) -> None:
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction))
        await interaction.edit_original_response(
            content=panel_text(data, feedback),
            embeds=[
                embed
                for embed in (profile_embed(data), plan_embed(data), opening_embed(data))
                if embed is not None
            ],
            view=SessionZeroView(service, interaction.user.id, data),
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except WorkflowError as error:
        await reply(interaction, str(error))


def panel_text(data: dict[str, Any], feedback: str) -> str:
    lines = ["**Session Zero**"]
    if feedback:
        lines.append(feedback)
    if not data["members"]:
        lines.append("Choose the campaign members taking part, including the prospective Handler.")
        return "\n".join(lines)
    approved = f"{data['approvals']} of {len(data['members'])} approvals"
    lines.append("Group · " + " ".join(f"<@{uid}>" for uid in data["members"]))
    if data.get("nominee"):
        lines.append(f"Handler nominee <@{data['nominee']}> · {approved}")
    else:
        lines.append(
            "Discuss the Handler together, then propose a profile for each member to approve."
        )
    if data["handler_ready"] is None:
        if data["approved"] and data["appointed"] is None:
            lines.append("A configured administrator can appoint the approved Handler.")
        elif data["approved"]:
            lines.append("Review the existing appointment with /campaign handler.")
    elif data["in_group"]:
        status = {"missing": "needs sheet", "attached": "attached", "refresh": "needs refresh"}
        lines.append(
            "**Pilot sheets** · "
            + "  ·  ".join(f"<@{uid}> {status[state]}" for uid, state in data["sheets"].items())
        )
        if data.get("input_status"):
            lines.append(
                "**Character input** · "
                + "  ·  ".join(
                    f"<@{uid}> " + ("✓ Filed" if state == "filed" else "Pending")
                    for uid, state in data["input_status"].items()
                )
            )
        lines.append(
            "Attach your current sheet to share its callsign and playbooks. "
            "Add character input to guide the campaign goals."
        )
    return "\n".join(lines)


def profile_embed(data: dict[str, Any]) -> discord.Embed | None:
    profile = data.get("profile")
    if not profile:
        return None
    embed = discord.Embed(title=f"{clean(profile['name'])} · {profile['archetype']}")
    embed.add_field(name="Appearance", value=clean(profile["appearance"]), inline=False)
    embed.add_field(name="Personality", value=clean(profile["personality"]), inline=False)
    return embed


def plan_embed(data: dict[str, Any]) -> discord.Embed | None:
    if not data.get("plan_proposal"):
        return None
    mode = data["difficulty"]
    embed = discord.Embed(
        title="Agreed campaign plan" if data["plan_approved"] else "Campaign plan for review",
        description=clean(data["goals"]),
    )
    embed.add_field(name="Difficulty", value=f"{mode.title()} · {DIFFICULTY_DESCRIPTIONS[mode]}")
    embed.add_field(name="Approvals", value=f"{data['plan_approvals']} of {len(data['members'])}")
    return embed


def opening_embed(data: dict[str, Any]) -> discord.Embed | None:
    record = data.get("opening")
    if not record:
        return None
    embed = discord.Embed(title="Cadre Introduction", description=clean(record["introduction"]))
    embed.add_field(name="Scene", value=f"<#{record['channel']}>")
    embed.add_field(name="Fictional day", value=str(data["opening_day"]))
    embed.add_field(name="First mission", value=f"From Day {record['first_mission_day']}")
    return embed


async def write_action(
    interaction: discord.Interaction,
    service: SessionZeroService,
    operation: Callable[[], object],
    feedback: str,
) -> None:
    if not await action_gate(interaction, "metadata"):
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        await asyncio.to_thread(operation)
    except ValidationError:
        feedback = "Fill in the required fields and check the length of each entry."
    except WorkflowError as error:
        feedback = str(error)
    await open_panel(interaction, service, feedback)


class SessionZeroView(discord.ui.View):
    def __init__(self, service: SessionZeroService, owner: int, data: dict[str, Any]):
        super().__init__(timeout=600)
        self.service, self.owner, self.data = service, owner, data
        if not data["admin"]:
            self.remove_item(self.group)
        if not data["in_group"]:
            for item in (
                self.propose,
                self.approve,
                self.attach,
                self.notes,
                self.goals,
                self.generate,
            ):
                self.remove_item(item)
        self.approve.disabled = data["proposal"] is None
        if data["own_approval"]:
            self.approve.label = "Withdraw my approval"
            self.approve.style = discord.ButtonStyle.secondary
        if not data["can_appoint"]:
            self.remove_item(self.appoint)
        if not data.get("sheets", {}).get(owner):
            self.remove_item(self.attach)
            self.remove_item(self.notes)
        self.attach.disabled = data.get("sheets", {}).get(owner) == "attached"
        self.notes.disabled = not self.attach.disabled
        if data["handler_ready"] != owner:
            self.remove_item(self.goals)
        self.generate.disabled = not data.get("can_generate")

        record = data.get("opening")
        is_handler = data["handler_ready"] == owner
        if record:
            for item in (self.group, self.propose, self.approve, self.goals):
                self.remove_item(item)
        if record or not data.get("plan_proposal"):
            self.remove_item(self.approve_plan)
        elif data.get("own_plan_approval"):
            self.approve_plan.label = "Withdraw plan approval"
            self.approve_plan.style = discord.ButtonStyle.secondary
        if not is_handler or record:
            self.remove_item(self.complete)
        self.complete.disabled = not bool(data.get("plan_approved") and data.get("can_generate"))
        if not is_handler or not record or data["opening_day"] >= record["first_mission_day"]:
            self.remove_item(self.advance)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "Open your own Session Zero panel with /session-zero.")
            return False
        return True

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]
    ) -> None:
        await reply(interaction, "Session Zero is unavailable. Reopen it to check saved progress.")

    @discord.ui.button(label="Choose group", row=0)
    async def group(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        await interaction.response.send_modal(GroupModal(self))

    @discord.ui.button(label="Propose Handler", row=0)
    async def propose(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.send_modal(HandlerModal(self))

    @discord.ui.button(label="Approve Handler proposal", style=discord.ButtonStyle.primary, row=0)
    async def approve(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        viewer = viewer_from_interaction(interaction)
        await write_action(
            interaction,
            self.service,
            lambda: self.service.decide(
                viewer,
                str(interaction.id),
                self.data["proposal"],
                approve=not self.data["own_approval"],
            ),
            "Your decision is saved.",
        )

    @discord.ui.button(label="Appoint approved Handler", row=0)
    async def appoint(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        viewer = viewer_from_interaction(interaction)
        await write_action(
            interaction,
            self.service,
            lambda: self.service.appoint(
                viewer,
                str(interaction.id),
                self.data["setup_revision"],
                self.data["proposal"],
                self.data["nominee"],
            ),
            "The approved Handler is appointed.",
        )

    @discord.ui.button(label="Attach my character sheet", row=1)
    async def attach(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        viewer = viewer_from_interaction(interaction)
        await write_action(
            interaction,
            self.service,
            lambda: self.service.attach(viewer, str(interaction.id), self.data["revision"]),
            "Your character sheet is attached.",
        )

    @discord.ui.button(label="Add character input", row=1)
    async def notes(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        await interaction.response.send_modal(NotesModal(self))

    @discord.ui.button(label="Draft goals and difficulty", row=1)
    async def goals(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        await interaction.response.send_modal(GoalsModal(self))

    @discord.ui.button(label="Approve campaign plan", style=discord.ButtonStyle.primary, row=3)
    async def approve_plan(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        viewer = viewer_from_interaction(interaction)
        await write_action(
            interaction,
            self.service,
            lambda: self.service.decide_plan(
                viewer,
                str(interaction.id),
                self.data["plan_proposal"],
                approve=not self.data["own_plan_approval"],
            ),
            "Your campaign plan decision is saved.",
        )

    @discord.ui.button(label="Complete and open introduction", row=3)
    async def complete(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.send_modal(OpeningModal(self))

    @discord.ui.button(label="Advance one roleplay day", row=3)
    async def advance(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        viewer = viewer_from_interaction(interaction)
        await write_action(
            interaction,
            self.service,
            lambda: self.service.advance_opening(
                viewer, str(interaction.id), self.data["opening_anchor"]
            ),
            "The fictional calendar advanced by one day.",
        )

    @discord.ui.button(
        label="Generate Session Zero sheet", style=discord.ButtonStyle.success, row=2
    )
    async def generate(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if not await action_gate(interaction, "metadata"):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            sheet = await asyncio.to_thread(
                self.service.generate, viewer_from_interaction(interaction), self.data["revision"]
            )
            with BytesIO(sheet.encode()) as buffer:
                document = discord.File(buffer, filename="session-zero.md")
                try:
                    await interaction.edit_original_response(
                        content="Your group’s Session Zero worksheet",
                        attachments=[document],
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                finally:
                    document.close()
        except WorkflowError as error:
            await open_panel(interaction, self.service, str(error))

    @discord.ui.button(label="Refresh", row=2)
    async def refresh(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await open_panel(interaction, self.service)


class SessionZeroModal(discord.ui.Modal):
    def __init__(self, panel: SessionZeroView, title: str):
        super().__init__(title=title, timeout=600)
        self.panel = panel

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await self.panel.interaction_check(interaction)

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item[Any] | None = None,
    ) -> None:
        await reply(interaction, "Session Zero is unavailable. Reopen it to check saved progress.")


class GroupModal(SessionZeroModal):
    def __init__(self, panel: SessionZeroView):
        super().__init__(panel, "Session Zero group")
        self.members: discord.ui.UserSelect[Any] = discord.ui.UserSelect(
            min_values=2,
            max_values=MAX_GROUP,
            required=True,
            default_values=[
                discord.SelectDefaultValue(id=uid, type=discord.SelectDefaultValueType.user)
                for uid in panel.data["members"]
            ],
        )
        self.add_item(
            discord.ui.Label(
                text="Handler and every Pilot",
                component=self.members,
                description="Choose joined campaign members. A new group needs fresh approvals.",
            )
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        viewer = viewer_from_interaction(interaction)
        await write_action(
            interaction,
            self.panel.service,
            lambda: self.panel.service.set_group(
                viewer,
                str(interaction.id),
                self.panel.data["revision"],
                tuple(person.id for person in self.members.values),
            ),
            "The Session Zero group is saved.",
        )


class HandlerModal(SessionZeroModal):
    def __init__(self, panel: SessionZeroView):
        super().__init__(panel, "Propose your group’s Handler")
        saved = panel.data.get("profile") or {}
        self.candidate: discord.ui.UserSelect[Any] = discord.ui.UserSelect(
            required=True,
            default_values=[
                discord.SelectDefaultValue(
                    id=saved["member"], type=discord.SelectDefaultValueType.user
                )
            ]
            if saved
            else [],
        )
        self.archetype: discord.ui.Select[Any] = discord.ui.Select(
            options=[
                discord.SelectOption(
                    label=entry,
                    value=entry,
                    default=entry == saved.get("archetype"),
                )
                for entry in PLAYBOOKS
            ],
        )
        self.name: discord.ui.TextInput[Any] = discord.ui.TextInput(
            max_length=100,
            default=saved.get("name"),
        )
        self.appearance: discord.ui.TextInput[Any] = discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            max_length=400,
            default=saved.get("appearance"),
        )
        self.personality: discord.ui.TextInput[Any] = discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            max_length=400,
            default=saved.get("personality"),
        )
        self.add_item(discord.ui.Label(text="Who plays the Handler?", component=self.candidate))
        self.add_item(discord.ui.Label(text="Handler archetype", component=self.archetype))
        self.add_item(discord.ui.Label(text="Handler's name", component=self.name))
        self.add_item(discord.ui.Label(text="Appearance", component=self.appearance))
        self.add_item(discord.ui.Label(text="Personality traits", component=self.personality))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        viewer = viewer_from_interaction(interaction)

        def operation() -> object:
            candidate = self.candidate.values[0]
            archetype: Playbook = next(x for x in PLAYBOOKS if x == self.archetype.values[0])
            return self.panel.service.propose(
                viewer,
                str(interaction.id),
                self.panel.data["revision"],
                HandlerProfile(
                    member=candidate.id,
                    player_name=candidate.display_name,
                    archetype=archetype,
                    name=self.name.value,
                    appearance=self.appearance.value,
                    personality=self.personality.value,
                ),
            )

        await write_action(
            interaction, self.panel.service, operation, "The Handler proposal is open for approval."
        )


class NotesModal(SessionZeroModal):
    def __init__(self, panel: SessionZeroView):
        super().__init__(panel, "Share character input")
        saved = panel.data.get("own_notes", {})
        self.goal: discord.ui.TextInput[Any] = discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            max_length=CHARACTER_NOTES_LIMIT,
            default=saved.get("goal"),
            required=False,
        )
        self.hook: discord.ui.TextInput[Any] = discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            max_length=CHARACTER_NOTES_LIMIT,
            default=saved.get("hook"),
            required=False,
        )
        self.spotlight: discord.ui.TextInput[Any] = discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            max_length=CHARACTER_NOTES_LIMIT,
            default=saved.get("spotlight"),
            required=False,
        )
        self.relationships: discord.ui.TextInput[Any] = discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            max_length=CHARACTER_NOTES_LIMIT,
            default=saved.get("relationships"),
            required=False,
        )
        self.add_item(discord.ui.Label(text="What does your character want?", component=self.goal))
        self.add_item(
            discord.ui.Label(text="What trouble or story hook can we use?", component=self.hook)
        )
        self.add_item(
            discord.ui.Label(text="What spotlight would you like?", component=self.spotlight)
        )
        self.add_item(
            discord.ui.Label(
                text="Relationships with other characters", component=self.relationships
            )
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        viewer = viewer_from_interaction(interaction)
        await write_action(
            interaction,
            self.panel.service,
            lambda: self.panel.service.notes(
                viewer,
                str(interaction.id),
                self.panel.data["revision"],
                CharacterNotes(
                    goal=self.goal.value,
                    hook=self.hook.value,
                    spotlight=self.spotlight.value,
                    relationships=self.relationships.value,
                ),
            ),
            "Your character input is saved for the group worksheet.",
        )


class GoalsModal(SessionZeroModal):
    def __init__(self, panel: SessionZeroView):
        super().__init__(panel, "Draft goals and difficulty")
        self.goals: discord.ui.TextInput[Any] = discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            max_length=800,
            default=panel.data.get("goals"),
            required=False,
        )
        self.mode: discord.ui.Select[Any] = discord.ui.Select(
            options=[
                discord.SelectOption(
                    label=mode.title(),
                    value=mode,
                    description=DIFFICULTY_DESCRIPTIONS[mode],
                    default=mode == panel.data.get("difficulty", DEFAULT_DIFFICULTY),
                )
                for mode in DIFFICULTIES
            ]
        )
        self.add_item(
            discord.ui.Label(text="What should the cadre aim for first?", component=self.goals)
        )
        self.add_item(discord.ui.Label(text="Campaign difficulty", component=self.mode))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        viewer = viewer_from_interaction(interaction)
        await write_action(
            interaction,
            self.panel.service,
            lambda: self.panel.service.goals(
                viewer,
                str(interaction.id),
                self.panel.data["revision"],
                self.goals.value,
                next(mode for mode in DIFFICULTIES if mode == self.mode.values[0]),
            ),
            "The campaign goal draft is saved.",
        )


class OpeningModal(SessionZeroModal):
    def __init__(self, panel: SessionZeroView):
        super().__init__(panel, "Open the cadre introduction")
        self.channel: discord.ui.ChannelSelect[Any] = discord.ui.ChannelSelect(
            channel_types=[discord.ChannelType.text],
            required=True,
        )
        self.account: discord.ui.TextInput[Any] = discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            max_length=1200,
        )
        self.days: discord.ui.Select[Any] = discord.ui.Select(
            options=[
                discord.SelectOption(
                    label=f"{days} fictional days",
                    value=str(days),
                    default=days == DEFAULT_ROLEPLAY_DAYS,
                )
                for days in range(2, 8)
            ]
        )
        self.add_item(discord.ui.Label(text="Existing roleplay channel", component=self.channel))
        self.add_item(
            discord.ui.Label(
                text="Handler's introduction to the cadre",
                component=self.account,
                description="Introduce yourself, explain the plan and invite discussion.",
            )
        )
        self.add_item(discord.ui.Label(text="Time before the first mission", component=self.days))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        viewer = viewer_from_interaction(interaction)
        await write_action(
            interaction,
            self.panel.service,
            lambda: self.panel.service.complete(
                viewer,
                str(interaction.id),
                self.panel.data["revision"],
                self.channel.values[0].id,
                self.account.value,
                int(self.days.values[0]),
            ),
            "The cadre introduction is open.",
        )


def register_session_zero(
    tree: app_commands.CommandTree, guild_id: int, service: SessionZeroService
) -> None:
    @tree.command(
        name="session-zero",
        description="Open your group's private Session Zero worksheet",
        guild=discord.Object(id=guild_id),
    )
    @app_commands.guild_only()
    async def session_zero(interaction: discord.Interaction) -> None:
        await open_panel(interaction, service)
