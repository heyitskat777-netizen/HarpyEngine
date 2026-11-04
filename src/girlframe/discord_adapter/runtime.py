"""Gateway lifecycle; secrets are passed directly and never logged."""

import asyncio
import signal

import discord
from pydantic import SecretStr

from girlframe.config import load_settings
from girlframe.database.connection import create_database_engine
from girlframe.discord_adapter.bot import ReadOnlyDiscordBot, quiet_sdk_logging
from girlframe.discord_adapter.config import BotPolicy
from girlframe.engine_adapter.snapshot import SandboxStatusSource
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import ReadOnlyBotService


def connection_failure_message(error: Exception) -> str:
    if isinstance(error, WorkflowError):
        return str(error)
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
        "and proxy connectivity. No engine operations are enabled."
    )


async def serve(policy: BotPolicy, token: SecretStr, proxy: str | None) -> None:
    quiet_sdk_logging()
    service = ReadOnlyBotService(policy, SandboxStatusSource(policy.sandbox))
    engine = create_database_engine(load_settings())
    try:
        store = OnboardingStore(engine, policy)
        await _connect(policy, service, proxy, token, store)
    finally:
        engine.dispose()


async def _connect(
    policy: BotPolicy,
    service: ReadOnlyBotService,
    proxy: str | None,
    token: SecretStr,
    store: OnboardingStore,
) -> None:
    async with ReadOnlyDiscordBot(policy, service, proxy, store) as bot:
        loop = asyncio.get_running_loop()
        installed_signal = False
        try:
            loop.add_signal_handler(
                signal.SIGTERM, lambda: asyncio.create_task(bot.close_for_restart())
            )
            installed_signal = True
        except (NotImplementedError, RuntimeError):
            # Windows / non-main-thread loops still support normal context cleanup.
            pass
        try:
            await bot.start(token.get_secret_value(), reconnect=True)
        finally:
            if installed_signal:
                loop.remove_signal_handler(signal.SIGTERM)
