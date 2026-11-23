"""Set up and launch private Activity campaigns with the HarpyEngine Discord bot."""

import argparse
import asyncio
import logging
import os
import sqlite3
import subprocess
from concurrent.futures import Future
from contextlib import contextmanager
from pathlib import Path
from threading import Thread

import discord
from aiohttp import ClientError
from discord import app_commands

from campaign_registry import RUNTIME, SNOWFLAKE, CampaignBindingError, CampaignRegistry

logger = logging.getLogger("harpy_activity.discord")


def create_from_interaction(
    registry,
    interaction,
    name,
    role,
    handler,
    *,
    guild=None,
    channel=None,
    provision=None,
):
    guild = guild if guild is not None else interaction.guild
    if guild is None or interaction.guild_id != guild.id:
        raise CampaignBindingError("Run this command in the Discord server.")
    if interaction.user.id != guild.owner_id:
        raise CampaignBindingError(
            "Only the Discord server owner can create a campaign."
        )
    if handler is not None and (handler.guild.id != guild.id or handler.bot):
        raise CampaignBindingError("Choose a human Handler in this Discord server.")
    return registry.register(
        application_id=str(interaction.application_id),
        guild_id=str(guild.id),
        owner_id=str(guild.owner_id),
        actor_id=str(interaction.user.id),
        role_id=str(role.id),
        role_guild_id=str(role.guild.id),
        handler_id=str(handler.id if handler else interaction.user.id),
        interaction_id=str(interaction.id),
        name=name,
        channel_id=str(channel.id) if channel else None,
        channel_guild_id=str(channel.guild.id) if channel else None,
        provision=provision,
    )


def setup_command(registry, provision):
    group = app_commands.Group(
        name="activity-campaign",
        description="Set up or launch a private HarpyEngine Activity campaign",
    )

    @group.command(
        name="create", description="Bind a new Activity campaign to a server role"
    )
    @app_commands.describe(
        name="Campaign name",
        role="Members with this role can enter",
        channel="Launching the Activity here opens this campaign",
        handler="The campaign Handler, defaults to the server owner",
    )
    async def create(
        interaction: discord.Interaction,
        name: app_commands.Range[str, 1, 80],
        role: discord.Role,
        channel: discord.TextChannel | discord.VoiceChannel,
        handler: discord.Member | None = None,
    ):
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Only the Discord server owner can create a campaign.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        try:
            guild = await interaction.client.fetch_guild(interaction.guild_id)
            if guild.owner_id != interaction.user.id:
                raise CampaignBindingError(
                    "Only the Discord server owner can create a campaign."
                )
            current_role = guild.get_role(role.id)
            if current_role is None:
                raise CampaignBindingError(
                    "Choose an existing Discord role from this server."
                )
            current_channel = await interaction.client.fetch_channel(channel.id)
            if (
                not isinstance(
                    current_channel, (discord.TextChannel, discord.VoiceChannel)
                )
                or current_channel.guild.id != guild.id
            ):
                raise CampaignBindingError(
                    "Choose a text or voice channel in this Discord server."
                )
            saved = await asyncio.to_thread(
                create_from_interaction,
                registry,
                interaction,
                name,
                current_role,
                handler,
                guild=guild,
                channel=current_channel,
                provision=provision,
            )
        except CampaignBindingError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return
        except discord.HTTPException:
            await interaction.followup.send(
                "Discord could not verify this server. Try again.", ephemeral=True
            )
            return
        except (
            OSError,
            RuntimeError,
            sqlite3.Error,
            subprocess.SubprocessError,
            ValueError,
        ):
            await interaction.followup.send(
                "HarpyEngine could not prepare the campaign store. Try again.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            f"Saved **{discord.utils.escape_markdown(saved.name)}** for role **{discord.utils.escape_markdown(role.name)}** "
            f"in **#{discord.utils.escape_markdown(channel.name)}**. "
            "Assign that role to the Handler and pilots so they can use "
            "`/activity-campaign launch` in the bound channel.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @group.command(name="launch", description="Open the campaign bound to this channel")
    async def launch(interaction: discord.Interaction):
        member = interaction.user
        if interaction.guild_id is None or not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "Run this command in the campaign's Discord server.", ephemeral=True
            )
            return
        try:
            bindings = await asyncio.wait_for(
                asyncio.to_thread(
                    registry.bindings,
                    str(interaction.application_id),
                    str(interaction.guild_id),
                ),
                timeout=1,
            )
        except (TimeoutError, sqlite3.Error):
            await interaction.response.send_message(
                "HarpyEngine could not read the campaign binding. Try again.",
                ephemeral=True,
            )
            return
        binding = next(
            (
                item
                for item in bindings
                if item.channel_id == str(interaction.channel_id)
            ),
            None,
        )
        if binding is None:
            await interaction.response.send_message(
                "This channel has no Activity campaign. Run the command in the bound channel.",
                ephemeral=True,
            )
            return
        if member.get_role(int(binding.role_id)) is None:
            await interaction.response.send_message(
                "You need the Discord role assigned to this channel's campaign.",
                ephemeral=True,
            )
            return
        await interaction.response.launch_activity()

    return group


def dm_command(include_user_installs):
    group = app_commands.Group(
        name="activity-campaign",
        description="Launch a private HarpyEngine Activity campaign in this DM",
        allowed_contexts=app_commands.AppCommandContext(
            guild=False, dm_channel=True, private_channel=include_user_installs
        ),
        allowed_installs=app_commands.AppInstallationType(
            guild=True, user=include_user_installs
        ),
    )

    @group.command(name="launch", description="Open your HarpyEngine campaign")
    async def launch(interaction: discord.Interaction):
        # A DM carries no server roles. Activity sign-in checks the private server.
        await interaction.response.launch_activity()

    return group


class SetupBot(discord.Client):
    def __init__(
        self, application_id, guild_id, registry, *, allow_dm=False, provision=None
    ):
        super().__init__(
            intents=discord.Intents(guilds=True), application_id=application_id
        )
        self.activity_id = application_id
        self.target = discord.Object(id=guild_id)
        self.allow_dm = allow_dm
        self.tree = app_commands.CommandTree(self)
        self.command = setup_command(registry, provision)
        self.tree.add_command(self.command, guild=self.target)

    async def setup_hook(self):
        info = await self.application_info()
        if info.id != self.activity_id:
            raise RuntimeError(
                "The bot token belongs to a different Discord application."
            )
        # Upsert only this group. A bulk sync would remove the bot's other guild commands.
        await self.http.upsert_guild_command(
            self.activity_id, self.target.id, self.command.to_dict(self.tree)
        )
        if self.allow_dm:
            command = dm_command(info.user_integration_config is not None)
            self.tree.add_command(command, override=True)
            await self.http.upsert_global_command(
                self.activity_id, command.to_dict(self.tree)
            )

    async def on_ready(self):
        logger.warning("Private Activity command listener connected.")
        print(
            "Campaign setup is connected. Run /activity-campaign launch in the bound channel.",
            flush=True,
        )


@contextmanager
def serve_commands(
    config, registry, token, provision, *, inbox_notices=None,
    notice_pending=None, scan_interactions=None,
):
    stopping = Future()

    async def listen():
        stopped = asyncio.wrap_future(stopping)
        while not stopped.done():
            try:
                async with SetupBot(
                    int(config.client_id),
                    int(config.guild_id),
                    registry,
                    allow_dm=config.allow_dm,
                    provision=provision,
                ) as bot:
                    gateway = asyncio.create_task(bot.start(token))
                    workers = []
                    if inbox_notices is not None:
                        from campaign_inbox import deliver_notices, scan_notices

                        workers.append(asyncio.create_task(
                            deliver_notices(bot, registry, inbox_notices, notice_pending)
                        ))
                        workers.append(asyncio.create_task(
                            scan_notices(bot, scan_interactions)
                        ))
                    try:
                        done, _ = await asyncio.wait(
                            (stopped, gateway), return_when=asyncio.FIRST_COMPLETED
                        )
                        if gateway in done:
                            gateway.result()
                    finally:
                        for task in (gateway, *workers):
                            task.cancel()
                        await asyncio.gather(gateway, *workers, return_exceptions=True)
                return
            except (discord.LoginFailure, RuntimeError):
                logger.error("Private Activity command credential failed validation.")
                return
            except (discord.DiscordException, OSError, TimeoutError) as error:
                logger.warning(
                    "Private Activity command listener will retry (%s).",
                    type(error).__name__,
                )
                await asyncio.wait((stopped,), timeout=15)

    worker = Thread(
        target=lambda: asyncio.run(listen()),
        name="discord-activity-commands",
        daemon=True,
    )
    worker.start()
    try:
        yield
    finally:
        stopping.set_result(None)
        worker.join(timeout=5)


async def verify_bot_token(token, application_id):
    try:
        async with discord.Client(intents=discord.Intents.none()) as client:
            await asyncio.wait_for(client.login(token), timeout=15)
    except discord.LoginFailure:
        print(
            "Discord rejected the bot token. Paste the current raw HarpyEngine bot token."
        )
        return 1
    except discord.HTTPException as error:
        print(
            f"Discord could not verify the bot token (HTTP {error.status}). Try again."
        )
        return 1
    except (ClientError, OSError, TimeoutError):
        print("The verification request could not reach Discord. Try again.")
        return 1
    if client.application_id != application_id:
        print("Discord verified the token for a different application.")
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--application-id", required=True)
    parser.add_argument("--guild-id", required=True)
    parser.add_argument(
        "--registry", type=Path, default=RUNTIME / "activity-campaigns.sqlite3"
    )
    parser.add_argument("--allow-dm", action="store_true")
    parser.add_argument("--check-token", action="store_true")
    args = parser.parse_args()
    if not SNOWFLAKE.fullmatch(args.application_id) or not SNOWFLAKE.fullmatch(
        args.guild_id
    ):
        parser.error("Provide the installed application and Discord server IDs.")
    token = os.environ.pop("GIRLFRAME_ACTIVITY_SETUP_BOT_TOKEN", None)
    if not token:
        parser.error(
            "Set GIRLFRAME_ACTIVITY_SETUP_BOT_TOKEN in the bot process environment."
        )
    if args.check_token:
        raise SystemExit(asyncio.run(verify_bot_token(token, int(args.application_id))))
    from mission_lab import provision_managed_campaign

    SetupBot(
        int(args.application_id),
        int(args.guild_id),
        CampaignRegistry(args.registry),
        allow_dm=args.allow_dm,
        provision=provision_managed_campaign,
    ).run(token)


if __name__ == "__main__":
    main()
