"""Assign only app-owned, zero-permission label roles and a requested nickname."""

from typing import Literal

import discord

from girlframe.services.character_tags import RoleCreationRefused, TagSyncIssue


class DiscordCharacterTagGateway:
    def __init__(self, guild: discord.Guild):
        self.guild = guild
        self.roles: dict[int, discord.Role] = {}
        self.member: discord.Member | None = None
        self.roles_dirty = False

    async def refresh_roles(self) -> None:
        self.roles = {role.id: role for role in await self.guild.fetch_roles()}
        self.roles_dirty = False

    def bot_top_role(self) -> discord.Role:
        if self.guild.me is None:
            raise TagSyncIssue("Bot guild membership is unavailable.")
        return max(self.roles.get(role.id, role) for role in self.guild.me.roles)

    async def member_ready(self, owner: int) -> None:
        try:
            self.member = await self.guild.fetch_member(owner)
            await self.refresh_roles()
        except discord.HTTPException:
            raise TagSyncIssue(
                "Member lookup failed. Ask the administrator to check guild access."
            ) from None

    async def safe_role_exists(self, identity: int, label: str | None = None) -> bool:
        if self.roles_dirty:
            await self.refresh_roles()
        role = self.roles.get(identity)
        if role is None:
            return False
        if label is not None and role.name != label:
            raise TagSyncIssue(
                "A managed label role was renamed; administrator review is required."
            )
        if role.managed or role.is_default() or role.permissions.value != 0:
            raise TagSyncIssue(
                "A managed label role has unsafe permissions; administrator review is required."
            )
        if role >= self.bot_top_role():
            raise TagSyncIssue("Move the bot's highest role above its character-tag roles.")
        return True

    async def create_tag_role(self, label: str) -> int:
        if self.guild.me is None or not self.guild.me.guild_permissions.manage_roles:
            raise RoleCreationRefused("Roles pending: the bot needs Manage Roles.")
        try:
            role = await self.guild.create_role(
                name=label,
                permissions=discord.Permissions.none(),
                hoist=False,
                mentionable=False,
                reason="HarpyEngine selected character tag",
            )
        except discord.HTTPException as error:
            if error.status < 500:
                raise RoleCreationRefused(
                    "Roles pending: check Manage Roles and role hierarchy."
                ) from None
            raise
        self.roles[role.id] = role
        self.roles_dirty = True
        return role.id

    async def apply_roles(self, owner: int, desired: set[int], managed: dict[int, str]) -> None:
        member = await self.guild.fetch_member(owner)
        present = {role.id for role in member.roles}
        removing = (present & set(managed)) - desired
        for identity in desired | removing:
            if not await self.safe_role_exists(identity, managed.get(identity)):
                raise TagSyncIssue("A character-tag role disappeared. Retry /character sync.")
        if (desired - present or removing) and (
            self.guild.me is None or not self.guild.me.guild_permissions.manage_roles
        ):
            raise TagSyncIssue("Roles pending: the bot needs Manage Roles.")
        try:
            if desired - present:
                await member.add_roles(
                    *(self.roles[identity] for identity in sorted(desired - present)),
                    reason="HarpyEngine confirmed character labels",
                    atomic=True,
                )
            if removing:
                await member.remove_roles(
                    *(self.roles[identity] for identity in sorted(removing)),
                    reason="HarpyEngine replaced its own character labels",
                    atomic=True,
                )
        except discord.HTTPException:
            raise TagSyncIssue(
                "Roles pending: Discord denied assignment; check role hierarchy."
            ) from None

    async def nickname(
        self, owner: int, callsign: str
    ) -> Literal["updated", "unchanged", "owner", "hierarchy"]:
        member = await self.guild.fetch_member(owner)
        if member.nick == callsign:
            return "unchanged"
        if member.id == self.guild.owner_id:
            return "owner"
        if self.guild.me is None or not self.guild.me.guild_permissions.manage_nicknames:
            raise TagSyncIssue("Nickname pending: the bot needs Manage Nicknames.")
        highest = max(self.roles.get(role.id, role) for role in member.roles)
        if highest >= self.bot_top_role():
            return "hierarchy"
        try:
            await member.edit(nick=callsign, reason="HarpyEngine confirmed character callsign")
        except discord.HTTPException:
            raise TagSyncIssue(
                "Nickname pending: Discord denied the change; check role hierarchy."
            ) from None
        return "updated"
