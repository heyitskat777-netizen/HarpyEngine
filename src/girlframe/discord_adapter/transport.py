"""Minimal private interaction-response contract, without Discord network calls."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from girlframe.engine.identity import RequestPrincipal, Snowflake


class PrivateResponse(BaseModel):
    """Future real adapters must disable mentions and use ephemeral responses."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    principal: RequestPrincipal
    interaction_id: Snowflake
    content: str = Field(min_length=1, max_length=2000)


class DiscordTransport(Protocol):
    async def respond_private(self, response: PrivateResponse) -> None:
        """Respond only to the authenticated interaction owner."""
        ...
