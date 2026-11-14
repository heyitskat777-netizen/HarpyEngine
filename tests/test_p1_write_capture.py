"""Unwired SQL capture prerequisite: evidence is not approval to freeze or commit."""

import json
import sqlite3
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from girlframe.config import Settings
from girlframe.database import tables as t
from girlframe.database.connection import create_database_engine
from girlframe.services.p1_write_capture import CaptureError, capture_writes


@pytest.mark.parametrize("schema", ("metadata", "migrations"))
def test_capture_sql_mutations_replacements_and_source_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, schema: str
) -> None:
    url = f"sqlite:///{tmp_path / 'capture.db'}"
    if schema == "migrations":
        monkeypatch.setenv("GIRLFRAME_DATABASE_URL", url)
        command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
    engine = create_database_engine(Settings(database_url=url))
    if schema == "metadata":
        t.metadata.create_all(engine)
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA recursive_triggers=ON")
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        with capture_writes(connection, exclusive_authorizer=True) as capture:
            connection.execute(t.campaigns.insert().values(id="synthetic", guild_id="11"))
            connection.execute(
                t.campaigns.update().where(t.campaigns.c.id == "synthetic").values(guild_id="22")
            )
            # Explicit rowid replacement must retain evidence of the implicit delete.
            rowid = connection.exec_driver_sql("SELECT rowid FROM campaigns").scalar_one()
            connection.exec_driver_sql(
                "INSERT OR REPLACE INTO campaigns(rowid, id, guild_id) VALUES (?, ?, ?)",
                (rowid, "replacement", "33"),
            )
            changes = capture.changes()
            assert [change.operation for change in changes] == [
                "insert",
                "update",
                "delete",
                "insert",
            ]
            assert all(change.table == "campaigns" for change in changes)
            assert json.loads(changes[1].before_key) == {"id": "synthetic"}
            assert json.loads(changes[1].before_row)["guild_id"] == "11"
            assert json.loads(changes[1].after_row)["guild_id"] == "22"
            assert json.loads(changes[2].before_row)["id"] == "synthetic"
            assert json.loads(changes[3].after_key) == {"id": "replacement"}
            assert "synthetic" not in repr(changes)
        with pytest.raises(CaptureError, match="closed"):
            capture.changes()
        assert (
            connection.exec_driver_sql("SELECT count(*) FROM sqlite_temp_master").scalar_one() == 0
        )
        connection.rollback()
        assert connection.scalar(sa.select(sa.func.count()).select_from(t.campaigns)) == 0
    engine.dispose()


def test_capture_denies_untracked_control_schema_and_log_tampering(tmp_path: Path) -> None:
    engine = create_database_engine(Settings(database_url=f"sqlite:///{tmp_path / 'denials.db'}"))
    t.metadata.create_all(engine)
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA recursive_triggers=ON")
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        with capture_writes(connection, exclusive_authorizer=True) as capture:
            connection.execute(t.campaigns.insert().values(id="synthetic", guild_id="11"))
            log = connection.exec_driver_sql(
                "SELECT name FROM sqlite_temp_master WHERE type='table'"
            ).scalar_one()
            for statement in (
                "COMMIT",
                "ROLLBACK",
                "SAVEPOINT not_a_permit",
                "CREATE TABLE unregistered (id TEXT)",
                "ALTER TABLE campaigns ADD COLUMN secret TEXT",
                "PRAGMA recursive_triggers=OFF",
                f'DELETE FROM temp."{log}"',
            ):
                with pytest.raises(
                    sa.exc.DatabaseError, match="not authorized|authorization denied"
                ):
                    connection.exec_driver_sql(statement)
            assert len(capture.changes()) == 1
        connection.rollback()
        # Cleanup releases exclusive hook; ordinary transactions still work.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        connection.execute(t.campaigns.insert().values(id="after", guild_id="22"))
        connection.rollback()
    engine.dispose()


def test_capture_rejects_unknown_schema_unsafe_defaults_and_excess_work(tmp_path: Path) -> None:
    engine = create_database_engine(Settings(database_url=f"sqlite:///{tmp_path / 'bounds.db'}"))
    t.metadata.create_all(engine)
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        with pytest.raises(CaptureError, match="requires recursive triggers"):
            with capture_writes(connection, exclusive_authorizer=True):
                pytest.fail("Unsafe replacement tracking was accepted")
        connection.exec_driver_sql("PRAGMA recursive_triggers=ON")
        connection.exec_driver_sql("CREATE TABLE unknown_table(id TEXT PRIMARY KEY)")
        with pytest.raises(CaptureError, match="Unknown or missing"):
            with capture_writes(connection, exclusive_authorizer=True):
                pytest.fail("Unknown schema was accepted")
        connection.exec_driver_sql("DROP TABLE unknown_table")
        with capture_writes(connection, exclusive_authorizer=True, max_changes=1) as capture:
            connection.execute(t.campaigns.insert().values(id="first", guild_id="11"))
            with pytest.raises(sa.exc.IntegrityError, match="capture limit exceeded"):
                connection.execute(t.campaigns.insert().values(id="over-limit", guild_id="22"))
            assert len(capture.changes()) == 1
            assert connection.scalar(sa.select(sa.func.count()).select_from(t.campaigns)) == 1
        connection.rollback()
    engine.dispose()


def test_implicit_rollback_blocks_following_autocommit_writes(tmp_path: Path) -> None:
    engine = create_database_engine(Settings(database_url=f"sqlite:///{tmp_path / 'implicit.db'}"))
    t.metadata.create_all(engine)
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA recursive_triggers=ON")
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        raw = connection.connection.driver_connection
        assert isinstance(raw, sqlite3.Connection)
        statement = (
            "WITH source(id, guild_id) AS (VALUES (?, ?)) "
            "INSERT INTO campaigns(id, guild_id) SELECT id, guild_id FROM source"
        )
        with pytest.raises(CaptureError, match="transaction ended"):
            with capture_writes(connection, exclusive_authorizer=True) as capture:
                # Prime the raw statement cache while the source transaction lives.
                raw.execute(statement, ("original", "11"))
                with pytest.raises(sa.exc.IntegrityError):
                    connection.exec_driver_sql(
                        "INSERT OR ROLLBACK INTO campaigns(id, guild_id) VALUES ('original', '22')"
                    )
                assert not raw.in_transaction
                # Catching the first failure must not allow an untracked durable
                # write after SQLite rolled back the TEMP capture triggers.
                with pytest.raises(CaptureError, match="transaction ended"):
                    connection.exec_driver_sql(statement, ("escaped", "33"))
                with pytest.raises(
                    sqlite3.DatabaseError, match="not authorized|authorization denied"
                ):
                    raw.execute(statement, ("raw-escaped", "44"))
                with pytest.raises(CaptureError, match="closed"):
                    capture.changes()
        connection.rollback()
        assert connection.scalar(sa.select(sa.func.count()).select_from(t.campaigns)) == 0
        assert (
            connection.exec_driver_sql("SELECT count(*) FROM sqlite_temp_master").scalar_one() == 0
        )
    with engine.connect() as reopened:
        assert reopened.scalar(sa.select(sa.func.count()).select_from(t.campaigns)) == 0
    engine.dispose()
