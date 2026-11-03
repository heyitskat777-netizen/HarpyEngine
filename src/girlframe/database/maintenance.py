"""Trusted local SQLite maintenance. New destinations only; never hot replace."""

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from sqlalchemy.engine import make_url

from girlframe.config import Settings


def database_path(settings: Settings) -> Path:
    database = make_url(settings.database_url).database
    if not database or database == ":memory:":
        raise ValueError("A persistent SQLite database is required")
    return Path(database).resolve()


def _verify(connection: sqlite3.Connection) -> None:
    if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise ValueError("Database integrity check failed")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise ValueError("Database foreign key check failed")
    if not connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
    ).fetchone():
        raise ValueError("Not a migrated application database")


def copy_database(source: Path, destination: Path) -> None:
    """WAL-consistent online backup, also used to restore to a NEW offline path."""
    source = source.resolve(strict=True)
    if not source.is_file() or source == destination.resolve():
        raise ValueError("Source must be a separate database file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation rejects existing files and symlinks, including the active DB.
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    try:
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src:
            with sqlite3.connect(destination) as dst:
                src.backup(dst)
                _verify(dst)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def write_export(destination: Path, content: dict[str, Any]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as output:
        os.chmod(destination, 0o600)
        json.dump(content, output, sort_keys=True, indent=2)
        output.write("\n")
