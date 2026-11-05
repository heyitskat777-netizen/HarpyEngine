"""Discord permission and publication adapter for explicitly bound scene channels."""

from typing import Any

import discord

from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_receipt_text import expression
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class DiscordGameGateway:
    def __init__(self, guild: discord.Guild, game: GameService):
        self.guild = guild
        self.game = game

    async def channel(self, identity: int) -> discord.TextChannel:
        channel = await self.guild.fetch_channel(identity)
        if not isinstance(channel, discord.TextChannel) or channel.guild.id != self.guild.id:
            raise WorkflowError("M2 scenes require a text channel in the configured guild.")
        me = self.guild.me
        if me is None:
            raise WorkflowError("Bot membership is unavailable.")
        p = channel.permissions_for(me)
        if not (p.view_channel and p.send_messages and p.manage_roles and p.read_message_history):
            raise WorkflowError(
                "Scene lock needs View Channel, Send Messages, Manage Roles and "
                "Read Message History."
            )
        return channel

    async def snapshot(self, channel: int, participants: list[int]) -> dict[str, Any]:
        resource = await self.channel(channel)
        for uid in participants:
            member = await self.guild.fetch_member(uid)
            if not resource.permissions_for(member).view_channel:
                raise WorkflowError("A scene participant cannot view this channel.")
        assert self.guild.me is not None
        return {
            "everyone_id": self.guild.id,
            "bot_id": self.guild.me.id,
            "overwrites": [
                {
                    "kind": "role" if isinstance(target, discord.Role) else "member",
                    "id": str(target.id),
                    "allow": overwrite.pair()[0].value,
                    "deny": overwrite.pair()[1].value,
                }
                for target, overwrite in resource.overwrites.items()
            ],
        }

    async def target(self, record: dict[str, Any]) -> discord.Role | discord.Member:
        uid = int(record["id"])
        if record["kind"] == "member":
            return await self.guild.fetch_member(uid)
        roles = await self.guild.fetch_roles()
        role = next((x for x in roles if x.id == uid), None)
        if role is None:
            raise WorkflowError("A snapshotted role was deleted; staff must reconcile the lock.")
        return role

    async def overwrite(self, channel: int, target: dict[str, Any]) -> dict[str, int] | None:
        resource = await self.channel(channel)
        for entity, overwrite in resource.overwrites.items():
            if str(entity.id) == str(target["id"]) and isinstance(entity, discord.Role) == (
                target["kind"] == "role"
            ):
                a, d = overwrite.pair()
                return {"allow": a.value, "deny": d.value}
        return None

    async def set_overwrite(
        self, channel: int, target: dict[str, Any], value: dict[str, int] | None
    ) -> None:
        resource = await self.channel(channel)
        overwrite = (
            discord.PermissionOverwrite.from_pair(
                discord.Permissions(value["allow"]), discord.Permissions(value["deny"])
            )
            if value is not None
            else None
        )
        await resource.set_permissions(
            await self.target(target),
            overwrite=overwrite,
            reason="HarpyEngine pending Play scene lock / restoration",
        )

    async def publish(self, channel: int, payload: dict[str, Any], nonce: str) -> int:
        return await self._publish(await self.channel(channel), payload, nonce, controls=True)

    async def _publish(
        self,
        resource: discord.abc.Messageable,
        payload: dict[str, Any],
        nonce: str,
        *,
        controls: bool,
    ) -> int:
        from girlframe.discord_adapter.m2_ui import SceneControls

        kind = payload["kind"]
        view = None
        if kind == "control":
            text = (
                "**Play pending — scene chat paused**\nOpen your private choices "
                "below. Safety pause is always available. Staff with Administrator "
                "permission can still post."
            )
            view = SceneControls(self.game) if controls else None
        elif kind == "receipt":
            receipt = payload["receipt"]
            text = (
                f"**{clean(payload['callsign'])} — {clean(payload['play'].replace('_', ' '))}**"
                f"\n{clean(expression(receipt))}"
                f" = {receipt['pre_total']} before Tags."
                f"\nReceipt `{receipt['id']}`\nHuman responses pending."
            )
        elif kind == "outcome":
            text = (
                f"**{clean(payload['callsign'])} — resolved**"
                f"\n{clean(payload['play'].replace('_', ' '))}"
            )
            if payload.get("total") is not None:
                text += f" · {payload['total']} · {clean(payload['tier'])}"
            text += (
                "\nRequired immediate choices are saved. Private details remain in "
                "the player's sheet."
            )
        else:
            text = "**Play aborted by staff.** Saved receipts and spent resources are preserved."
        text += "\nM2 delivery `" + nonce + "`"
        if view is not None:
            message = await resource.send(
                text, nonce=nonce, view=view, allowed_mentions=discord.AllowedMentions.none()
            )
        else:
            message = await resource.send(
                text, nonce=nonce, allowed_mentions=discord.AllowedMentions.none()
            )
        return message.id

    async def _private(self, recipient: int) -> discord.DMChannel:
        member = await self.guild.fetch_member(recipient)
        with self.game.store.engine.connect() as c:
            self.game.authorize(
                c,
                GuildViewer(member.id, self.guild.id, True, member.guild_permissions.administrator),
                game=False,
            )
        return await member.create_dm()

    async def publish_private(self, recipient: int, payload: dict[str, Any], nonce: str) -> int:
        return await self._publish(await self._private(recipient), payload, nonce, controls=False)

    async def find_private(self, recipient: int, nonce: str) -> int | None:
        resource = await self._private(recipient)
        async for message in resource.history(limit=50):
            if (
                self.guild.me
                and message.author.id == self.guild.me.id
                and ("M2 delivery `" + nonce + "`") in message.content
            ):
                return message.id
        return None

    async def find(self, channel: int, nonce: str) -> int | None:
        resource = await self.channel(channel)
        async for message in resource.history(limit=50):
            if (
                self.guild.me
                and message.author.id == self.guild.me.id
                and ("M2 delivery `" + nonce + "`") in message.content
            ):
                return message.id
        return None

    async def actor(self, identity: int) -> GuildViewer:
        member = await self.guild.fetch_member(identity)
        return GuildViewer(member.id, self.guild.id, True, member.guild_permissions.administrator)
