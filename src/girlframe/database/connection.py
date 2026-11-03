"""Single-writer local SQLite connection setup; never auto-migrate."""

import sqlite3
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import make_url

from girlframe.config import Settings


def create_database_engine(settings: Settings) -> Engine:
    database = make_url(settings.database_url).database
    if database and database != ":memory:":
        Path(database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(settings.database_url)

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection: sqlite3.Connection, _record: object) -> None:
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()

    return engine


def check_database(settings: Settings) -> None:
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            if connection.scalar(text("SELECT 1")) != 1:
                raise RuntimeError("Unexpected SQLite health response")
    finally:
        engine.dispose()
