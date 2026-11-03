import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from girlframe.config import Settings
from girlframe.database.base import Base
from girlframe.database.connection import create_database_engine

ROOT = Path(__file__).resolve().parents[1]


def test_sqlite_settings_and_foreign_keys(tmp_path: Path) -> None:
    engine = create_database_engine(Settings(database_url=f"sqlite:///{tmp_path / 'db.sqlite'}"))
    try:
        with engine.begin() as connection:
            assert connection.scalar(text("PRAGMA journal_mode")) == "wal"
            assert connection.scalar(text("PRAGMA foreign_keys")) == 1
            assert connection.scalar(text("PRAGMA busy_timeout")) == 5000
            # Synthetic, disposable tables only; no application schema in M0.
            connection.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))"))
            with pytest.raises(IntegrityError):
                connection.execute(text("INSERT INTO child VALUES (999)"))
    finally:
        engine.dispose()


def test_alembic_migrations_upgrade_check_and_downgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "migration.sqlite"
    monkeypatch.setenv("GIRLFRAME_DATABASE_URL", f"sqlite:///{db}")
    config = Config(str(ROOT / "alembic.ini"))
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    command.check(config)
    command.downgrade(config, "base")
    assert len(Base.metadata.tables) == 9
    engine = create_database_engine(Settings(database_url=f"sqlite:///{db}"))
    try:
        assert inspect(engine).get_table_names() == ["alembic_version"]
    finally:
        engine.dispose()
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM alembic_version").fetchone() == (0,)
