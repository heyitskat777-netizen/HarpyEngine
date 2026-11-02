"""Offline foundation health; never represents campaign or bot readiness."""

from typing import TypedDict

from girlframe.discord_adapter.transport import DiscordTransport, PrivateResponse
from girlframe.engine.identity import RequestContext


class FoundationHealth(TypedDict):
    milestone: str
    status: str
    database_checked: bool
    discord_connected: bool
    rules_implemented: bool


def foundation_health(*, database_checked: bool = False) -> FoundationHealth:
    return {
        "milestone": "M0",
        "status": "foundation_ok",
        "database_checked": database_checked,
        "discord_connected": False,
        "rules_implemented": False,
    }


async def respond_health(context: RequestContext, transport: DiscordTransport) -> None:
    """Exercise the service/adapter seam with no DB access or private state."""
    await transport.respond_private(
        PrivateResponse(
            principal=context.principal,
            interaction_id=context.interaction_id,
            content="M0 foundation only; Discord runtime and game rules are not implemented.",
        )
    )
