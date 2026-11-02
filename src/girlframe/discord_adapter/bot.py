"""Guild-scoped Gateway bot. No mutating game commands or passive message ingestion."""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

import discord
from discord import app_commands

from girlframe.discord_adapter.config import BotPolicy
from girlframe.services.engine_status import EngineStatusUnavailable
from girlframe.services.read_only_bot import (
    CommandDenied,
    GuildViewer,
    ReadOnlyBotService,
    ReadOnlyCommand,
)


def viewer_from_interaction(interaction: discord.Interaction[discord.Client]) -> GuildViewer:
    member = isinstance(interaction.user, discord.Member)
    return GuildViewer(
        user_id=interaction.user.id,
        guild_id=interaction.guild_id,
        is_member=member,
        is_administrator=(
            interaction.user.guild_permissions.administrator
            if isinstance(interaction.user, discord.Member)
            else False
        ),
    )


class PrivateInteractionResponder:
    """Always private, with mentions disabled on both initial and deferred replies."""

    def __init__(self, interaction: discord.Interaction[discord.Client]) -> None:
        self.interaction = interaction

    async def defer(self) -> None:
        await self.interaction.response.defer(ephemeral=True, thinking=True)

    async def send(self, content: str) -> None:
        if self.interaction.response.is_done():
            await self.interaction.edit_original_response(
                content=content, allowed_mentions=discord.AllowedMentions.none()
            )
        else:
            await self.interaction.response.send_message(
                content, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
            )


async def dispatch_read_only(
    command: ReadOnlyCommand,
    viewer: GuildViewer,
    responder: PrivateInteractionResponder,
    service: ReadOnlyBotService,
) -> None:
    try:
        service.authorize(command, viewer)
    except CommandDenied as error:
        await responder.send(str(error))
        return
    # Acknowledge before reading local files; never block Gateway heartbeats.
    await responder.defer()
    try:
        content = await asyncio.to_thread(service.execute, command, viewer)
    except CommandDenied:
        content = "Access denied."
    except EngineStatusUnavailable:
        content = "Engine status is unavailable. Ask the administrator to check the sandbox."
    except Exception:
        content = "Command unavailable. Ask the administrator to check the bot."
    await responder.send(content)


class ReadOnlyCommandTree(app_commands.CommandTree[discord.Client]):
    async def on_error(
        self, interaction: discord.Interaction[discord.Client], error: app_commands.AppCommandError
    ) -> None:
        # SDK exceptions may contain paths, interaction tokens or raw payloads.
        try:
            message = (
                "Please wait before using this command again."
                if isinstance(error, app_commands.CommandOnCooldown)
                else "Command unavailable. Try again later."
            )
            await PrivateInteractionResponder(interaction).send(message)
        except discord.HTTPException:
            pass


class ReadOnlyDiscordBot(discord.Client):
    def __init__(self, policy: BotPolicy, service: ReadOnlyBotService, proxy: str | None) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(
            intents=intents,
            application_id=policy.application_id,
            allowed_mentions=discord.AllowedMentions.none(),
            proxy=proxy,
        )
        self.policy = policy
        self.service = service
        self.tree = ReadOnlyCommandTree(self, fallback_to_global=False)
        guild = discord.Object(id=policy.guild_id)
        commands: tuple[tuple[ReadOnlyCommand, str], ...] = (
            ("help", "Show read-only bot usage"),
            ("campaign_status", "Show approved campaign status privately"),
            ("health", "Check read-only service health (administrators only)"),
        )
        for name, description in commands:
            callback = self._callback(name)
            command: app_commands.Command[Any, ..., None] = app_commands.Command(
                name=name, description=description, callback=callback
            )
            command = app_commands.checks.cooldown(
                3, 10.0, key=lambda interaction: (interaction.guild_id, interaction.user.id)
            )(command)
            command.guild_only = True
            if name == "health":
                command.default_permissions = discord.Permissions(administrator=True)
            self.tree.add_command(command, guild=guild)

    def _callback(
        self, name: ReadOnlyCommand
    ) -> Callable[[discord.Interaction[discord.Client]], Coroutine[Any, Any, None]]:
        async def callback(interaction: discord.Interaction[discord.Client]) -> None:
            await dispatch_read_only(
                name,
                viewer_from_interaction(interaction),
                PrivateInteractionResponder(interaction),
                self.service,
            )

        return callback

    async def setup_hook(self) -> None:
        info = await self.application_info()
        if info.id != self.policy.application_id:
            raise RuntimeError("Configured application does not match bot credentials")
        await self.fetch_guild(self.policy.guild_id)
        await self.tree.sync(guild=discord.Object(id=self.policy.guild_id))

    async def on_ready(self) -> None:
        print(
            "Discord bot ready: read-only commands registered in the configured test guild.",
            flush=True,
        )

    async def on_error(self, event_method: str, *args: object, **kwargs: object) -> None:
        print("A Discord event could not be handled; no game state was changed.", flush=True)


def quiet_sdk_logging() -> None:
    # Do not enable SDK debug logging: it can include interaction credentials.
    logger = logging.getLogger("discord")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
