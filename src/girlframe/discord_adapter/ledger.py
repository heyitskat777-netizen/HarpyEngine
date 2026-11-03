"""Private slash views plus explicit public roll delivery to the managed ledger."""

from typing import Any

import discord
from discord import app_commands

from girlframe.engine.rolls import RollReceipt
from girlframe.services.character_tags import CharacterTagSynchronizer
from girlframe.services.ledger import CampaignLedger
from girlframe.services.onboarding import WorkflowError


def clean(value: object) -> str:
    return discord.utils.escape_markdown(discord.utils.escape_mentions(str(value)))


def receipt_text(receipt: RollReceipt) -> str:
    return (
        f"**Raw 2d6 test — {clean(receipt.callsign)}**\n"
        f"{receipt.faces[0]} + {receipt.faces[1]} = **{receipt.total}**\n"
        f"Receipt `{receipt.id}`\n{receipt.rolled_utc}\n"
        "Test primitive; no official Play, modifiers or mechanical effects."
    )


def status_text(status: dict[str, Any]) -> str:
    return (
        f"**{clean(status['name'])}** — "
        f"{'safety paused' if status['paused'] else 'ready for raw dice tests'}\n"
        f"Members: {status['members']} · revision {status['revision']}\n"
        "M1 draft sandbox. Official Plays and recovered-engine writes are disabled."
    )


def register_ledger(
    tree: app_commands.CommandTree,
    guild_id: int,
    ledger: CampaignLedger,
    tags: CharacterTagSynchronizer | None,
) -> None:
    from girlframe.discord_adapter.bot import viewer_from_interaction
    from girlframe.discord_adapter.onboarding import open_draft, private_operation

    guild = discord.Object(id=guild_id)
    campaign = tree.get_command("campaign", guild=guild)
    assert isinstance(campaign, app_commands.Group)

    @campaign.command(name="create", description="Initialize the campaign name; administrator only")
    async def create(interaction: discord.Interaction, name: str) -> None:
        def operation() -> str:
            viewer = viewer_from_interaction(interaction)
            ledger.administrator(viewer)
            result = ledger.create_campaign(
                viewer, str(interaction.id), ledger.status(viewer)["revision"], name
            )
            return f"Campaign initialized: {clean(result['name'])}. Existing drafts were preserved."

        await private_operation(interaction, operation)

    @campaign.command(name="status", description="Show this bot's stored campaign status")
    async def status(interaction: discord.Interaction) -> None:
        await private_operation(
            interaction, lambda: status_text(ledger.status(viewer_from_interaction(interaction)))
        )

    girl = app_commands.Group(name="girl", description="Saved draft wizard", guild_only=True)

    @girl.command(name="create", description="Choose playbooks and create or edit your own draft")
    async def girl_create(interaction: discord.Interaction) -> None:
        await open_draft(interaction, ledger, tags)

    roll = app_commands.Group(name="roll", description="Recorded raw dice tests", guild_only=True)

    @roll.command(
        name="basic", description="Record raw 2d6; optionally publish to rolls-and-ledger"
    )
    @app_commands.describe(
        publish="Post the receipt publicly to the managed ledger (default: private)"
    )
    async def basic(interaction: discord.Interaction, publish: bool = False) -> None:
        def operation() -> str:
            viewer = viewer_from_interaction(interaction)
            receipt = ledger.roll_basic(
                viewer, str(interaction.id), ledger.status(viewer)["revision"], publish=publish
            )
            suffix = "\nPublic ledger delivery queued." if publish else "\nPrivate receipt."
            return receipt_text(receipt) + suffix

        await private_operation(interaction, operation)

    @roll.command(name="show", description="Retrieve a recorded receipt you are allowed to view")
    async def show(interaction: discord.Interaction, receipt: str) -> None:
        await private_operation(
            interaction,
            lambda: receipt_text(
                ledger.get_roll_receipt(viewer_from_interaction(interaction), receipt)
            ),
        )

    @app_commands.command(
        name="ledger", description="List permitted events; use before to paginate"
    )
    @app_commands.guild_only()
    async def events(interaction: discord.Interaction, before: int | None = None) -> None:
        def operation() -> str:
            rows = ledger.list_events(viewer_from_interaction(interaction), before=before)
            if not rows:
                return "No permitted ledger entries on this page."
            return (
                "**Campaign ledger**\n"
                + "\n".join(
                    f"#{r['seq']} {r['kind']}" + (f" · `{r['roll_id']}`" if r["roll_id"] else "")
                    for r in rows
                )
                + f"\nNext page: /ledger before:{rows[-1]['seq']}"
            )

        await private_operation(interaction, operation)

    safety = app_commands.Group(
        name="safety", description="Campaign OOC safety pause", guild_only=True
    )

    async def safety_action(interaction: discord.Interaction, pause: bool) -> None:
        def operation() -> str:
            viewer = viewer_from_interaction(interaction)
            result = ledger.safety(
                viewer, str(interaction.id), ledger.status(viewer)["revision"], pause=pause
            )
            if pause:
                return "Your safety pause is saved. New rolls are blocked; no reason is required."
            return (
                "Your pause was cleared. Other participants still have a pause active."
                if result["paused"]
                else "Your pause was cleared. Raw dice tests can resume."
            )

        # Safety bypasses the ordinary metadata throttle; always acknowledge promptly.
        import asyncio

        from girlframe.discord_adapter.onboarding import reply

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            text = await asyncio.to_thread(operation)
        except WorkflowError as error:
            text = str(error)
        except Exception:
            text = "Safety request could not be saved. Stop play and contact an administrator."
        await reply(interaction, text)

    @safety.command(
        name="pause", description="Pause new rolls without a reason or fictional penalty"
    )
    async def pause(interaction: discord.Interaction) -> None:
        await safety_action(interaction, True)

    @safety.command(name="resume", description="Clear only your own pause; others remain active")
    async def resume(interaction: discord.Interaction) -> None:
        await safety_action(interaction, False)

    commands: tuple[app_commands.Group | app_commands.Command[Any, ..., Any], ...] = (
        girl,
        roll,
        events,
        safety,
    )
    for command in commands:
        tree.add_command(command, guild=guild)


class DiscordRollGateway:
    def __init__(self, guild: discord.Guild):
        self.guild = guild

    async def _channel(self, channel_id: int) -> discord.TextChannel:
        channel = await self.guild.fetch_channel(channel_id)
        if not isinstance(channel, discord.TextChannel) or channel.guild.id != self.guild.id:
            raise WorkflowError("Managed ledger unavailable.")
        me = self.guild.me
        if me is None:
            raise WorkflowError("Bot guild membership unavailable.")
        permissions = channel.permissions_for(me)
        if not (permissions.view_channel and permissions.send_messages):
            raise WorkflowError("Ledger delivery permissions unavailable.")
        return channel

    async def reconcile(self, channel_id: int, receipt_id: str) -> int | None:
        channel = await self._channel(channel_id)
        assert self.guild.me is not None
        if not channel.permissions_for(self.guild.me).read_message_history:
            return None
        # Bounded recovery in the dedicated ledger only; never ingest roleplay channels.
        async for message in channel.history(limit=50):
            if (
                message.author.id == self.guild.me.id
                and f"Receipt `{receipt_id}`" in message.content
            ):
                return message.id
        return None

    async def send(self, channel_id: int, receipt: RollReceipt, nonce: str) -> int:
        channel = await self._channel(channel_id)
        message = await channel.send(
            receipt_text(receipt), nonce=nonce, allowed_mentions=discord.AllowedMentions.none()
        )
        return message.id
