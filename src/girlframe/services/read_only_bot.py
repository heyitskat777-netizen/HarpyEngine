"""Read-only bot authorization and responses, independent of Discord SDK objects."""

from dataclasses import dataclass
from typing import Literal

from girlframe.discord_adapter.config import BotPolicy
from girlframe.services.engine_status import EngineStatusSource, get_engine_status

ReadOnlyCommand = Literal["help", "campaign_status", "health"]


@dataclass(frozen=True)
class GuildViewer:
    user_id: int
    guild_id: int | None
    is_member: bool
    is_administrator: bool
    role_ids: frozenset[int] = frozenset()


class CommandDenied(RuntimeError):
    pass


@dataclass(frozen=True)
class ReadOnlyBotService:
    policy: BotPolicy
    source: EngineStatusSource

    def authorize(self, command: ReadOnlyCommand, viewer: GuildViewer) -> None:
        if (
            command not in {"help", "campaign_status", "health"}
            or viewer.guild_id != self.policy.guild_id
            or not viewer.is_member
            or viewer.user_id <= 0
        ):
            raise CommandDenied("This command is unavailable here.")
        if command == "help":
            return
        administrator = viewer.is_administrator and self.policy.allow_guild_administrators
        if command == "health":
            if not administrator:
                raise CommandDenied("This command requires configured administrator access.")
            return
        if not self.policy.status_audience_approved or not (
            administrator or viewer.user_id in self.policy.status_user_ids
        ):
            raise CommandDenied("You do not have campaign status access.")

    def execute(self, command: ReadOnlyCommand, viewer: GuildViewer) -> str:
        self.authorize(command, viewer)
        if command == "help":
            return (
                "HarpyEngine — private campaign test bot.\n"
                "/help — usage\n/campaign_status — approved campaign status\n"
                "/health — configured administrators only\n"
                "/server setup — administrator preview and confirmation\n"
                "/campaign join — join as yourself\n/character create — save or resume a draft\n"
                "/sheet — your private sheet or another member's public sheet\n"
                "No rolls, engine writes, AI, or player actions are enabled. "
                "Contact your server administrator for access."
            )
        status = get_engine_status(self.source)
        if command == "health":
            return "Read-only command handler responsive; configured engine sandbox readable."
        mode = "paused" if status.paused else "active"
        return f"Campaign turn {status.turn} ({mode})."
