"""Trusted local bot policy. Credentials are loaded separately, never from JSON."""

import json
import os
from collections.abc import Mapping
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

from girlframe.engine.identity import Snowflake


class BotPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    application_id: Snowflake
    guild_id: Snowflake
    campaign_id: UUID
    sandbox: Path
    status_user_ids: frozenset[Snowflake] = frozenset()
    allow_guild_administrators: bool = False
    status_audience_approved: bool = False

    @field_validator("sandbox")
    @classmethod
    def absolute_sandbox(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("An absolute disposable runtime path is required")
        return value


def load_bot_policy(path: Path) -> BotPolicy:
    # model_validate_json permits JSON representations of Path/UUID/frozenset,
    # while strict mode still rejects string IDs, boolean IDs and coerced flags.
    with path.open("rb") as source:
        data = source.read(64 * 1024 + 1)
    if len(data) > 64 * 1024:
        raise ValueError("Bot policy is too large")
    return BotPolicy.model_validate_json(data)


def load_bot_token(environ: Mapping[str, str] | None = None) -> SecretStr:
    values = os.environ if environ is None else environ
    raw = values.get("DiscordBot")
    if not raw or not raw.strip():
        raise ValueError("DiscordBot is not configured")
    return SecretStr(raw.strip())


def policy_summary(policy: BotPolicy) -> str:
    """Safe startup evidence; no filesystem paths or roster IDs."""
    return json.dumps({"mode": "m1_draft_ledger", "guild_scoped": True, "commands": 11})
