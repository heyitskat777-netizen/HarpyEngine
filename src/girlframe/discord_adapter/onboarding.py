"""Explicit setup confirmation, persistent intake controls and private draft forms."""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

import discord
from discord import app_commands
from pydantic import ValidationError

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.engine.drafts import DraftInput
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.provisioning import (
    TEMPLATE,
    CreationRefused,
    Provisioner,
    ResourceSpec,
)

_action_buckets: OrderedDict[tuple[int | None, int, str], tuple[float, int]] = OrderedDict()


def allow_action(guild: int | None, user: int, action: str, now: float | None = None) -> bool:
    """Bounded, process-local transport throttling; not an authorization mechanism."""
    current = time.monotonic() if now is None else now
    key = (guild, user, action)
    start, count = _action_buckets.get(key, (current, 0))
    if current - start >= 10:
        start, count = current, 0
    if count >= 3:
        return False
    _action_buckets[key] = (start, count + 1)
    _action_buckets.move_to_end(key)
    if len(_action_buckets) > 4096:
        _action_buckets.popitem(last=False)
    return True


async def action_gate(interaction: discord.Interaction, action: str) -> bool:
    if allow_action(interaction.guild_id, interaction.user.id, action):
        return True
    await reply(interaction, "Please wait a few seconds before trying this action again.")
    return False


async def reply(
    interaction: discord.Interaction, text: str, view: discord.ui.View | None = None
) -> None:
    if interaction.response.is_done():
        await interaction.edit_original_response(
            content=text, view=view, allowed_mentions=discord.AllowedMentions.none()
        )
    elif view is not None:
        await interaction.response.send_message(
            text, ephemeral=True, view=view, allowed_mentions=discord.AllowedMentions.none()
        )
    else:
        await interaction.response.send_message(
            text, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )


async def private_operation(interaction: discord.Interaction, operation: Callable[[], str]) -> None:
    if not await action_gate(interaction, "metadata"):
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        text = await asyncio.to_thread(operation)
    except WorkflowError as error:
        text = str(error)
    except Exception:
        text = "This action is unavailable. Ask the administrator to check database setup."
    await reply(interaction, text)


def sheet_text(data: dict[str, Any] | None) -> str:
    if data is None:
        return "No draft saved yet. Use /character create."

    def clean(value: object) -> str:
        return discord.utils.escape_markdown(discord.utils.escape_mentions(str(value)))

    text = (
        "**Character draft — rules unverified**\n"
        f"ID: {data['id']} | revision {data['revision']}\n"
        f"Callsign: {clean(data['callsign'])}\n"
        f"Proposed Girl playbook: {clean(data['girl_playbook'])}\n"
        f"Proposed Frame playbook: {clean(data['frame_playbook'])}\n"
        "Not activated for official gameplay."
    )
    if "notes" in data:
        text += f"\nPrivate notes: {clean(data['notes']) or '(none)'}"
    return text if len(text) <= 1900 else text[:1897] + "..."


class SaveDraftView(discord.ui.View):
    def __init__(self, store: OnboardingStore, owner: int, revision: int, draft: DraftInput):
        super().__init__(timeout=300)
        self.store, self.owner, self.revision, self.draft = store, owner, revision, draft

    @discord.ui.button(label="Save draft", style=discord.ButtonStyle.success)
    async def save(
        self, interaction: discord.Interaction, button: discord.ui.Button[SaveDraftView]
    ) -> None:
        viewer = viewer_from_interaction(interaction)

        def operation() -> str:
            if viewer.user_id != self.owner:
                raise WorkflowError("This draft confirmation belongs to another player.")
            result = self.store.save_draft(viewer, str(interaction.id), self.revision, self.draft)
            return (
                f"Saved draft {result['id']} (revision {result['revision']}). "
                "Use /sheet to view or /character create to resume. Rules remain unverified."
            )

        await private_operation(interaction, operation)


class DraftModal(discord.ui.Modal, title="Character draft — rules unverified"):
    def __init__(self, store: OnboardingStore, owner: int, existing: dict[str, Any] | None):
        super().__init__(timeout=300)
        self.store, self.owner = store, owner
        data = existing or {}
        self.revision = int(data.get("revision", 0))
        self.callsign: discord.ui.TextInput[Any] = discord.ui.TextInput(
            label="Callsign", max_length=40, default=data.get("callsign")
        )
        self.girl: discord.ui.TextInput[Any] = discord.ui.TextInput(
            label="Proposed Girl playbook", max_length=60, default=data.get("girl_playbook")
        )
        self.frame: discord.ui.TextInput[Any] = discord.ui.TextInput(
            label="Proposed Frame playbook", max_length=60, default=data.get("frame_playbook")
        )
        self.notes: discord.ui.TextInput[Any] = discord.ui.TextInput(
            label="Private notes (optional)",
            max_length=1000,
            style=discord.TextStyle.paragraph,
            required=False,
            default=data.get("notes"),
        )
        for item in (self.callsign, self.girl, self.frame, self.notes):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await action_gate(interaction, "draft_preview"):
            return
        viewer = viewer_from_interaction(interaction)
        try:
            self.store.guild_member(viewer)
            if viewer.user_id != self.owner:
                raise WorkflowError("This form belongs to another player.")
            draft = DraftInput(
                callsign=str(self.callsign),
                girl_playbook=str(self.girl),
                frame_playbook=str(self.frame),
                notes=str(self.notes),
            )
        except (WorkflowError, ValidationError):
            await reply(interaction, "Invalid draft or form owner. Reopen /character create.")
            return
        preview = sheet_text(
            {**draft.model_dump(), "id": "pending save", "revision": self.revision + 1}
        )
        await reply(
            interaction, preview, SaveDraftView(self.store, self.owner, self.revision, draft)
        )


async def open_draft(interaction: discord.Interaction, store: OnboardingStore) -> None:
    if not await action_gate(interaction, "draft_form"):
        return
    viewer = viewer_from_interaction(interaction)
    try:
        existing = await asyncio.wait_for(asyncio.to_thread(store.draft, viewer), timeout=2)
        await interaction.response.send_modal(DraftModal(store, viewer.user_id, existing))
    except WorkflowError as error:
        await reply(interaction, str(error))
    except Exception:
        await reply(interaction, "Draft form unavailable. Please try again shortly.")


class NewPlayerView(discord.ui.View):
    def __init__(self, store: OnboardingStore):
        super().__init__(timeout=None)
        self.store = store

    @discord.ui.button(
        label="Join campaign", style=discord.ButtonStyle.success, custom_id="harpyengine:join:v1"
    )
    async def join(
        self, interaction: discord.Interaction, button: discord.ui.Button[NewPlayerView]
    ) -> None:
        def operation() -> str:
            self.store.join(viewer_from_interaction(interaction), str(interaction.id))
            return "Joined this campaign. Use Create/Edit draft to start your character."

        await private_operation(interaction, operation)

    @discord.ui.button(label="Create/Edit draft", custom_id="harpyengine:draft:v1")
    async def draft(
        self, interaction: discord.Interaction, button: discord.ui.Button[NewPlayerView]
    ) -> None:
        await open_draft(interaction, self.store)

    @discord.ui.button(label="My sheet", custom_id="harpyengine:sheet:v1")
    async def sheet(
        self, interaction: discord.Interaction, button: discord.ui.Button[NewPlayerView]
    ) -> None:
        await private_operation(
            interaction, lambda: sheet_text(self.store.draft(viewer_from_interaction(interaction)))
        )


class DiscordProvisioningGateway:
    def __init__(self, guild: discord.Guild, entry: NewPlayerView):
        self.guild, self.entry = guild, entry
        self.channels: dict[int, Any] = {}

    def missing_permissions(self) -> list[str]:
        permissions = (
            self.guild.me.guild_permissions if self.guild.me else discord.Permissions.none()
        )
        return [
            name
            for name in ("view_channel", "send_messages", "manage_channels")
            if not getattr(permissions, name)
        ]

    async def preflight(self) -> None:
        if self.missing_permissions():
            raise CreationRefused(
                "Bot needs View Channels, Send Messages and Manage Channels. "
                "Rerun setup after granting them."
            )
        self.channels = {channel.id: channel for channel in await self.guild.fetch_channels()}

    def overwrites(
        self, spec: ResourceSpec
    ) -> dict[discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite]:
        member = self.guild.me
        if member is None:
            raise CreationRefused("Bot guild membership is not ready.")
        return {
            self.guild.default_role: discord.PermissionOverwrite(
                view_channel=not spec.private, send_messages=not spec.private and not spec.read_only
            ),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }

    async def exists(self, identity: int, spec: ResourceSpec, parent: int | None) -> bool:
        if spec.kind == "message":
            channel = self.channels.get(parent or 0)
            # Saved own-message IDs are trusted metadata. Do not acquire history
            # permission or read channel transcripts to revalidate that mapping.
            # If an admin deletes the message, slash-command fallbacks still work.
            return isinstance(channel, discord.TextChannel)
        channel = self.channels.get(identity)
        if channel is None:
            return False
        expected_type = discord.CategoryChannel if spec.kind == "category" else discord.TextChannel
        if not isinstance(channel, expected_type) or channel.category_id != parent:
            raise WorkflowError("A managed resource was moved or changed type. Review it manually.")
        expected = {
            target.id: overwrite.pair() for target, overwrite in self.overwrites(spec).items()
        }
        actual = {target.id: overwrite.pair() for target, overwrite in channel.overwrites.items()}
        if expected != actual:
            raise WorkflowError("Managed channel permissions changed. Review them before resuming.")
        return True

    async def create(self, spec: ResourceSpec, parent: int | None) -> int:
        try:
            if spec.kind == "category":
                channel = await self.guild.create_category(
                    spec.name,
                    overwrites=self.overwrites(spec),
                    reason="HarpyEngine confirmed server setup v1",
                )
                self.channels[channel.id] = channel
                return channel.id
            category = self.channels.get(parent or 0)
            if spec.kind == "text":
                if not isinstance(category, discord.CategoryChannel):
                    raise CreationRefused("Setup category is unavailable.")
                text = await self.guild.create_text_channel(
                    spec.name,
                    category=category,
                    overwrites=self.overwrites(spec),
                    reason="HarpyEngine confirmed server setup v1",
                )
                self.channels[text.id] = text
                return text.id
            if not isinstance(category, discord.TextChannel):
                raise CreationRefused("New-player channel is unavailable.")
            message = await category.send(
                "**Welcome to HarpyEngine**\nJoin the campaign, then create or resume your draft. "
                "Forms and sheets are private. Drafts are saved but not yet rules-validated.",
                view=self.entry,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return message.id
        except discord.HTTPException as error:
            if error.status < 500:
                print(
                    f"Setup API refusal: HTTP {error.status}, Discord code {error.code}", flush=True
                )
                raise CreationRefused(
                    "Discord refused resource creation. Partial setup is saved; "
                    "check permissions/limits and retry."
                ) from None
            raise


class SetupConfirmView(discord.ui.View):
    def __init__(self, provisioner: Provisioner, plan: str, guild: discord.Guild):
        super().__init__(timeout=600)
        self.provisioner, self.plan, self.guild = provisioner, plan, guild

    @discord.ui.button(label="Create missing setup resources", style=discord.ButtonStyle.success)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button[SetupConfirmView]
    ) -> None:
        if not await action_gate(interaction, "setup_confirm"):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            store = self.provisioner.store
            gateway = DiscordProvisioningGateway(self.guild, NewPlayerView(store))
            count = await self.provisioner.apply(
                viewer_from_interaction(interaction), self.plan, gateway
            )
            await reply(
                interaction,
                f"Setup complete: {count} resources created; saved resources reused. "
                "Onboarding message ID saved; use the new-player controls or /campaign join.",
            )
        except WorkflowError as error:
            await reply(interaction, str(error))
        except Exception:
            await reply(
                interaction,
                "Setup interrupted. Saved resources remain; "
                "ask the administrator to inspect before retrying.",
            )


def register_onboarding(
    tree: app_commands.CommandTree, guild_id: int, store: OnboardingStore, provisioner: Provisioner
) -> None:
    guild = discord.Object(id=guild_id)
    server = app_commands.Group(
        name="server",
        description="Administrator server provisioning",
        guild_only=True,
        default_permissions=discord.Permissions(administrator=True),
    )

    @server.command(
        name="setup", description="Preview missing HarpyEngine channels; confirm before creating"
    )
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: (i.guild_id, i.user.id))
    async def setup(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            viewer = viewer_from_interaction(interaction)
            store.administrator(viewer)
            if interaction.guild is None:
                raise WorkflowError("Guild context unavailable.")
            result = await asyncio.to_thread(store.create_plan, viewer, str(interaction.id))
            gateway = DiscordProvisioningGateway(interaction.guild, NewPlayerView(store))
            missing = gateway.missing_permissions()
            layout = "\n".join(f"• {spec.name}" for spec in TEMPLATE if spec.kind != "message")
            text = (
                "**Server setup preview (v1)**\n"
                + layout
                + "\nCreates missing managed resources only. Unrelated resources are unchanged. "
                "Staff resources are hidden from @everyone. New-player controls will be posted. "
                "Confirmation expires in ten minutes."
            )
            if missing:
                await reply(
                    interaction, text + "\n**Missing bot permissions:** " + ", ".join(missing)
                )
            else:
                await reply(
                    interaction,
                    text,
                    SetupConfirmView(provisioner, result["plan_id"], interaction.guild),
                )
        except WorkflowError as error:
            await reply(interaction, str(error))
        except Exception:
            await reply(interaction, "Setup preview unavailable. Check database migrations.")

    campaign = app_commands.Group(
        name="campaign", description="Campaign membership", guild_only=True
    )

    @campaign.command(name="join", description="Join this server's campaign as yourself")
    async def join(interaction: discord.Interaction) -> None:
        def operation() -> str:
            store.join(viewer_from_interaction(interaction), str(interaction.id))
            return "Joined. Use /character create to create or resume your draft."

        await private_operation(interaction, operation)

    character = app_commands.Group(
        name="character", description="Saved character drafts", guild_only=True
    )

    @character.command(name="create", description="Create or resume your private character draft")
    async def create(interaction: discord.Interaction) -> None:
        await open_draft(interaction, store)

    @app_commands.command(
        name="sheet", description="Show your private sheet or another member's public sheet"
    )
    @app_commands.guild_only()
    async def sheet(interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        await private_operation(
            interaction,
            lambda: sheet_text(
                store.draft(viewer_from_interaction(interaction), member.id if member else None)
            ),
        )

    registered: list[app_commands.Group | app_commands.Command[Any, ..., Any]] = [
        server,
        campaign,
        character,
        sheet,
    ]
    for command in registered:
        tree.add_command(command, guild=guild)
