"""Gateway lifecycle; secrets are passed directly and never logged."""

import asyncio
import signal

import discord
from pydantic import SecretStr

from girlframe.discord_adapter.bot import ReadOnlyDiscordBot, quiet_sdk_logging
from girlframe.discord_adapter.config import BotPolicy
from girlframe.engine_adapter.snapshot import SandboxStatusSource
from girlframe.services.read_only_bot import ReadOnlyBotService


def connection_failure_message(error: Exception) -> str:
    if isinstance(error, discord.LoginFailure):
        return "Discord rejected the bot credentials. Update DiscordBot securely and retry."
    if isinstance(error, discord.NotFound) and error.code == 10004:
        return (
            "Discord cannot access the configured guild (404/10004). "
            "Install the bot or verify the guild ID."
        )
    if isinstance(error, discord.Forbidden):
        return "Discord denied access. Check bot installation, command scope and guild permissions."
    return (
        "Discord startup/connection failed. Check credentials, application/guild access "
        "and proxy connectivity. No game state was changed."
    )


async def serve(policy: BotPolicy, token: SecretStr, proxy: str | None) -> None:
    quiet_sdk_logging()
    service = ReadOnlyBotService(policy, SandboxStatusSource(policy.sandbox))
    async with ReadOnlyDiscordBot(policy, service, proxy) as bot:
        loop = asyncio.get_running_loop()
        installed_signal = False
        try:
            loop.add_signal_handler(signal.SIGTERM, lambda: asyncio.create_task(bot.close()))
            installed_signal = True
        except (NotImplementedError, RuntimeError):
            # Windows / non-main-thread loops still support normal context cleanup.
            pass
        try:
            await bot.start(token.get_secret_value(), reconnect=True)
        finally:
            if installed_signal:
                loop.remove_signal_handler(signal.SIGTERM)
