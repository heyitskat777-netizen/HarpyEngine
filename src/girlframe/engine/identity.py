"""Transport-independent identity supplied by a future authenticated adapter."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Snowflake = Annotated[int, Field(strict=True, gt=0, lt=2**64)]


class RequestPrincipal(BaseModel):
    """An identity, not proof of campaign membership or authorization.

    M1 must resolve membership and authority server-side. Do not deserialize
    player-authored text into a trusted principal.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    user_id: Snowflake
    guild_id: Snowflake


class RequestContext(BaseModel):
    """Scope for future commands; carries no authority claims or mutations."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    principal: RequestPrincipal
    campaign_id: UUID
    interaction_id: Snowflake
