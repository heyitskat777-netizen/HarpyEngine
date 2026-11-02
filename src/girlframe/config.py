"""Explicit, minimal local configuration; no credential loading in M0."""

import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.engine import make_url


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    database_url: str = "sqlite:///./var/girlframe.db"
    engine_sandbox: Path | None = None

    @field_validator("engine_sandbox", mode="before")
    @classmethod
    def absolute_sandbox(cls, value: object) -> Path | None:
        if value is None:
            return None
        if not isinstance(value, (str, Path)):
            raise ValueError("An absolute local sandbox path is required")
        path = Path(value)
        if not path.is_absolute():
            raise ValueError("An absolute local sandbox path is required")
        return path

    @field_validator("database_url")
    @classmethod
    def local_sqlite_only(cls, value: str) -> str:
        url = make_url(value)
        if (
            url.drivername != "sqlite"
            or url.host is not None
            or url.username is not None
            or url.password is not None
            or url.port is not None
            or url.query
            or not url.database
        ):
            raise ValueError("M0 requires a plain local sqlite:/// URL")
        return value


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    values = os.environ if environ is None else environ
    sandbox = values.get("GIRLFRAME_ENGINE_SANDBOX")
    return Settings(
        database_url=values.get("GIRLFRAME_DATABASE_URL", Settings().database_url),
        engine_sandbox=Path(sandbox) if sandbox is not None else None,
    )
