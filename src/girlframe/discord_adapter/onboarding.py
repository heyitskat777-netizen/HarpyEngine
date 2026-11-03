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
from girlframe.discord_adapter.character_tags import DiscordCharacterTagGateway
from girlframe.engine.drafts import DraftInput
from girlframe.engine.playbooks import FRAME_TYPES, GIRL_TYPES, canonical_frame, canonical_girl
from girlframe.services.character_tags import CharacterTagSynchronizer
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
    limit = 20 if action == "inbox_read" else 3
    if count >= limit:
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
    def __init__(
        self,
        store: OnboardingStore,
        owner: int,
        revision: int,
        draft: DraftInput,
        tags: CharacterTagSynchronizer | None = None,
    ):
        super().__init__(timeout=300)
        self.store, self.owner, self.revision, self.draft = store, owner, revision, draft
        self.tags = tags

    @discord.ui.button(label="Save draft", style=discord.ButtonStyle.success)
    async def save(
        self, interaction: discord.Interaction, button: discord.ui.Button[SaveDraftView]
    ) -> None:
        if not await action_gate(interaction, "metadata"):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        viewer = viewer_from_interaction(interaction)
        try:
            if viewer.user_id != self.owner:
                raise WorkflowError("This draft confirmation belongs to another player.")
            result = await asyncio.to_thread(
                self.store.save_draft, viewer, str(interaction.id), self.revision, self.draft
            )
            text = (
                f"Saved draft {result['id']} (revision {result['revision']}). "
                "Use /sheet to view or /character create to resume. Rules remain unverified."
            )
        except WorkflowError as error:
            await reply(interaction, str(error))
            return
        except Exception:
            await reply(
                interaction,
                "Draft save unavailable. Reopen your sheet to check its current revision.",
            )
            return
        if self.tags is not None and interaction.guild is not None:
            try:
                text += "\n" + await self.tags.sync(
                    viewer, DiscordCharacterTagGateway(interaction.guild)
                )
            except Exception:
                text += (
                    "\nDraft is saved; Discord tags remain queued. Use /character sync to retry."
                )
        await reply(interaction, text)


class PlaybookSelect(discord.ui.Select["CharacterSelectionView"]):
    def __init__(self, family: str, selected: str | None):
        self.family = family
        catalog = GIRL_TYPES if family == "girl" else FRAME_TYPES
        super().__init__(
            placeholder="Choose Girl type" if family == "girl" else "Choose Frame type",
            options=[
                discord.SelectOption(label=label, value=value, default=value == selected)
                for value, label in catalog.items()
            ],
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        await self.view.choose(self.family, self.values[0], interaction)


class ContinueCharacterButton(discord.ui.Button["CharacterSelectionView"]):
    def __init__(self, disabled: bool):
        super().__init__(
            label="Continue: callsign and notes",
            style=discord.ButtonStyle.primary,
            disabled=disabled,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        await self.view.details(interaction)


class CharacterSelectionView(discord.ui.View):
    def __init__(
        self,
        store: OnboardingStore,
        owner: int,
        existing: dict[str, Any] | None,
        tags: CharacterTagSynchronizer | None = None,
    ):
        super().__init__(timeout=600)
        self.store, self.owner, self.existing, self.tags = store, owner, existing, tags
        data = existing or {}
        try:
            self.girl: str | None = canonical_girl(data.get("girl_playbook", ""))
        except ValueError:
            self.girl = None
        try:
            self.frame: str | None = canonical_frame(data.get("frame_playbook", ""))
        except ValueError:
            self.frame = None
        self.add_item(PlaybookSelect("girl", self.girl))
        self.add_item(PlaybookSelect("frame", self.frame))
        self.continue_button = ContinueCharacterButton(disabled=not (self.girl and self.frame))
        self.add_item(self.continue_button)

    def owner_check(self, interaction: discord.Interaction) -> None:
        viewer = viewer_from_interaction(interaction)
        self.store.guild_member(viewer)
        if viewer.user_id != self.owner:
            raise WorkflowError("This character selector belongs to another player.")

    def summary(self) -> str:
        return (
            "**Choose character labels**\n"
            f"Girl: {self.girl or 'not selected'}\nFrame: {self.frame or 'not selected'}\n"
            "Continue to enter the callsign and private notes. Saving assigns cosmetic Girl/Frame "
            "roles and requests the callsign as your server nickname. Rules remain unverified."
        )

    async def choose(self, family: str, value: str, interaction: discord.Interaction) -> None:
        try:
            self.owner_check(interaction)
            if family == "girl":
                self.girl = canonical_girl(value)
            elif family == "frame":
                self.frame = canonical_frame(value)
            else:
                raise ValueError("Unknown choice")
        except (WorkflowError, ValueError):
            await reply(interaction, "Use the listed choices on your own character selector.")
            return
        self.continue_button.disabled = not (self.girl and self.frame)
        await interaction.response.edit_message(
            content=self.summary(), view=self, allowed_mentions=discord.AllowedMentions.none()
        )

    async def details(self, interaction: discord.Interaction) -> None:
        try:
            self.owner_check(interaction)
            if not self.girl or not self.frame:
                raise WorkflowError("Choose both dropdowns first.")
            await interaction.response.send_modal(
                DraftModal(self.store, self.owner, self.existing, self.girl, self.frame, self.tags)
            )
        except WorkflowError as error:
            await reply(interaction, str(error))


class DraftModal(discord.ui.Modal, title="Character draft — rules unverified"):
    def __init__(
        self,
        store: OnboardingStore,
        owner: int,
        existing: dict[str, Any] | None,
        girl: str | None = None,
        frame: str | None = None,
        tags: CharacterTagSynchronizer | None = None,
    ):
        super().__init__(timeout=300)
        self.store, self.owner = store, owner
        data = existing or {}
        self.girl_value = canonical_girl(girl or data.get("girl_playbook", ""))
        self.frame_value = canonical_frame(frame or data.get("frame_playbook", ""))
        self.tags = tags
        self.revision = int(data.get("revision", 0))
        self.callsign: discord.ui.TextInput[Any] = discord.ui.TextInput(
            label="Callsign / server nickname", max_length=32, default=data.get("callsign", "")[:32]
        )
        self.notes: discord.ui.TextInput[Any] = discord.ui.TextInput(
            label="Private notes (optional)",
            max_length=1000,
            style=discord.TextStyle.paragraph,
            required=False,
            default=data.get("notes"),
        )
        for item in (self.callsign, self.notes):
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
                girl_playbook=self.girl_value,
                frame_playbook=self.frame_value,
                notes=str(self.notes),
            )
        except (WorkflowError, ValidationError):
            await reply(interaction, "Invalid draft or form owner. Reopen /character create.")
            return
        preview = sheet_text(
            {**draft.model_dump(), "id": "pending save", "revision": self.revision + 1}
        )
        await reply(
            interaction,
            preview + "\nSaving applies the selected label roles and server nickname.",
            SaveDraftView(self.store, self.owner, self.revision, draft, self.tags),
        )


async def open_draft(
    interaction: discord.Interaction,
    store: OnboardingStore,
    tags: CharacterTagSynchronizer | None = None,
) -> None:
    if not await action_gate(interaction, "draft_form"):
        return
    viewer = viewer_from_interaction(interaction)
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        existing = await asyncio.wait_for(asyncio.to_thread(store.draft, viewer), timeout=2)
        view = CharacterSelectionView(store, viewer.user_id, existing, tags)
        await reply(interaction, view.summary(), view)
    except WorkflowError as error:
        await reply(interaction, str(error))
    except Exception:
        await reply(interaction, "Draft form unavailable. Please try again shortly.")


class NewPlayerView(discord.ui.View):
    def __init__(self, store: OnboardingStore, tags: CharacterTagSynchronizer | None = None):
        super().__init__(timeout=None)
        self.store = store
        self.tags = tags

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
        await open_draft(interaction, self.store, self.tags)

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
    def __init__(
        self,
        provisioner: Provisioner,
        plan: str,
        guild: discord.Guild,
        tags: CharacterTagSynchronizer | None = None,
    ):
        super().__init__(timeout=600)
        self.provisioner, self.plan, self.guild = provisioner, plan, guild
        self.tags = tags

    @discord.ui.button(label="Create missing setup resources", style=discord.ButtonStyle.success)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button[SetupConfirmView]
    ) -> None:
        if not await action_gate(interaction, "setup_confirm"):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            store = self.provisioner.store
            gateway = DiscordProvisioningGateway(self.guild, NewPlayerView(store, self.tags))
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
    tree: app_commands.CommandTree,
    guild_id: int,
    store: OnboardingStore,
    provisioner: Provisioner,
    tags: CharacterTagSynchronizer | None = None,
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
            gateway = DiscordProvisioningGateway(interaction.guild, NewPlayerView(store, tags))
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
                    SetupConfirmView(provisioner, result["plan_id"], interaction.guild, tags),
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
        await open_draft(interaction, store, tags)

    @character.command(
        name="sync", description="Retry your saved character roles and server nickname"
    )
    async def sync(interaction: discord.Interaction) -> None:
        if not await action_gate(interaction, "metadata"):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            viewer = viewer_from_interaction(interaction)
            await asyncio.to_thread(store.queue_sync, viewer, str(interaction.id))
            if tags is None or interaction.guild is None:
                raise WorkflowError(
                    "Character tags are queued; the Discord synchronizer is unavailable."
                )
            message = await tags.sync(viewer, DiscordCharacterTagGateway(interaction.guild))
            await reply(interaction, message)
        except WorkflowError as error:
            await reply(interaction, str(error))
        except Exception:
            await reply(
                interaction,
                "The draft is saved; Discord tags are pending. Try /character sync later.",
            )

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
