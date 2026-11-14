"""Cooperative preparation plumbing only; no source/worker/freeze authority."""

import json
import sqlite3

import pytest
import sqlalchemy as sa
from test_p1_effect_journal import preparation, seed
from test_p1_guarded_source import database

from girlframe.database import tables as t
from girlframe.database.connection import create_database_engine
from girlframe.services.p1_effect_journal import prepare
from girlframe.services.p1_guarded_source import run_guarded_source
from girlframe.services.p1_write_capture import CaptureError, source_savepoint


def test_real_journal_prepare_partial_failure_retry_and_replay_inside_guarded_source(tmp_path):
    settings = database(tmp_path)
    captured = []

    def operation(connection, _principal):
        seed(connection)
        reader = connection.info["p1_write_capture"]
        initial = reader.changes()

        def fail_actor(_connection, _cursor, statement, *_args):
            if statement.startswith("INSERT INTO " + t.external_effects["actors"].name):
                raise RuntimeError("synthetic atomic step failure")

        sa.event.listen(connection, "before_cursor_execute", fail_actor)
        try:
            with pytest.raises(RuntimeError, match="synthetic atomic"):
                prepare(connection, "test", preparation())
        finally:
            sa.event.remove(connection, "before_cursor_execute", fail_actor)
        assert reader.changes() == initial
        for table in t.external_effects.values():
            assert connection.scalar(sa.select(sa.func.count()).select_from(table)) == 0
        effect = prepare(connection, "test", preparation())
        before_replay = reader.changes()
        assert prepare(connection, "test", preparation()) == effect
        assert reader.changes() == before_replay
        return effect

    def validate(changes, principal):
        assert principal == "synthetic-only"
        assert [x.table for x in changes] == [
            t.campaigns.name,
            t.events.name,
            t.external_effects["resources"].name,
            t.external_effects["effects"].name,
            t.external_effects["actors"].name,
            t.external_effects["links"].name,
        ]
        captured.extend(changes)
        return "synthetic-shape-only"

    committed = run_guarded_source(
        settings, authorize=lambda _: "synthetic-only", operation=operation, validate=validate
    )
    engine = create_database_engine(settings)
    with engine.connect() as connection:
        row = connection.execute(sa.select(t.external_effects["effects"])).mappings().one()
        assert row["id"] == committed.result and row["state"] == "prepared"
    engine.dispose()
    assert len(captured) == 6


def test_nested_steps_rollback_data_and_evidence_but_keep_outer_writes(tmp_path):
    settings = database(tmp_path)

    def insert(connection, identity, guild):
        connection.execute(t.campaigns.insert().values(id=identity, guild_id=guild))

    def operation(connection, _principal):
        insert(connection, "outer", "1")
        with source_savepoint(connection):
            insert(connection, "kept", "2")
            with pytest.raises(ValueError, match="cancel inner"):
                with source_savepoint(connection):
                    insert(connection, "rolled-back", "3")
                    raise ValueError("cancel inner")
            connection.execute(
                t.campaigns.update().where(t.campaigns.c.id == "kept").values(guild_id="4")
            )
            connection.execute(
                t.campaigns.update().where(t.campaigns.c.id == "kept").values(guild_id="2")
            )
        insert(connection, "after", "5")

    def validate(changes, _principal):
        assert [x.operation for x in changes] == ["insert", "insert", "update", "update", "insert"]
        assert [json.loads(x.after_key)["id"] for x in changes] == [
            "outer",
            "kept",
            "kept",
            "kept",
            "after",
        ]
        return "synthetic-only"

    run_guarded_source(settings, authorize=lambda _: None, operation=operation, validate=validate)
    engine = create_database_engine(settings)
    with engine.connect() as connection:
        assert set(connection.scalars(sa.select(t.campaigns.c.id))) == {"outer", "kept", "after"}
    engine.dispose()


def test_raw_and_cached_savepoint_controls_remain_denied(tmp_path):
    settings = database(tmp_path)

    def operation(connection, _principal):
        raw = connection.connection.driver_connection
        statements = []
        raw.set_trace_callback(statements.append)
        with source_savepoint(connection):
            with pytest.raises(CaptureError, match="Finish every"):
                connection.info["p1_write_capture"].changes()
            for sql in ("SAVEPOINT rogue", "COMMIT", "ROLLBACK"):
                with pytest.raises(sqlite3.DatabaseError):
                    raw.execute(sql)
            with pytest.raises(sa.exc.DatabaseError):
                connection.begin_nested()
        controls = [x for x in statements if x.startswith(("SAVEPOINT", "RELEASE SAVEPOINT"))]
        assert len(controls) == 2
        raw.set_trace_callback(None)
        # Replay exact previously authorized text, including SQLite's statement cache.
        for sql in controls:
            with pytest.raises(sqlite3.DatabaseError):
                raw.execute(sql)
        assert raw.in_transaction
        connection.execute(t.campaigns.insert().values(id="kept", guild_id="1"))

    def validate(changes, _principal):
        assert len(changes) == 1 and changes[0].table == t.campaigns.name
        return "synthetic-only"

    run_guarded_source(settings, authorize=lambda _: None, operation=operation, validate=validate)


def test_implicit_outer_rollback_inside_managed_step_invalidates_capture(tmp_path):
    settings = database(tmp_path)

    def operation(connection, _principal):
        connection.execute(t.campaigns.insert().values(id="original", guild_id="1"))
        with pytest.raises(CaptureError):
            with source_savepoint(connection):
                with pytest.raises(sa.exc.IntegrityError):
                    connection.exec_driver_sql(
                        "INSERT OR ROLLBACK INTO campaigns(id,guild_id) VALUES ('original','2')"
                    )
        # Swallowing the step failure cannot yield valid evidence or commit.
        return "not valid"

    with pytest.raises(CaptureError):
        run_guarded_source(
            settings,
            authorize=lambda _: None,
            operation=operation,
            validate=lambda *_: pytest.fail("Invalid source must not validate"),
        )
    engine = create_database_engine(settings)
    with engine.connect() as connection:
        assert connection.scalar(sa.select(sa.func.count()).select_from(t.campaigns)) == 0
    engine.dispose()
