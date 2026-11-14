"""Transaction mechanics only: synthetic callbacks are not authenticated gameplay."""

import json
from pathlib import Path

import pytest
import sqlalchemy as sa

from girlframe.config import Settings
from girlframe.database import tables as t
from girlframe.database.connection import create_database_engine
from girlframe.services import p1_guarded_source
from girlframe.services.p1_guarded_source import (
    SourceCommittedCleanupError,
    SourceTransactionError,
    run_guarded_source,
)
from girlframe.services.p1_write_capture import CaptureError


def database(tmp_path: Path) -> Settings:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'source.db'}")
    engine = create_database_engine(settings)
    t.metadata.create_all(engine)
    engine.dispose()
    return settings


def saved(settings: Settings) -> list[dict]:
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            return [dict(row) for row in connection.execute(sa.select(t.campaigns)).mappings()]
    finally:
        engine.dispose()


def validate_single_insert(changes, principal):
    assert principal == "synthetic-only"
    assert len(changes) == 1
    change = changes[0]
    assert (change.table, change.operation) == ("campaigns", "insert")
    assert json.loads(change.after_key) == {"id": "source"}
    return "synthetic-shape-only"


def test_guarded_source_captures_first_write_validates_then_commits(tmp_path):
    settings = database(tmp_path)
    seen = []

    def authorize(connection):
        assert connection.exec_driver_sql("SELECT count(*) FROM campaigns").scalar_one() == 0
        seen.append("authorize")
        return "synthetic-only"

    def operation(connection, principal):
        assert principal == "synthetic-only"
        connection.execute(t.campaigns.insert().values(id="source", guild_id="11"))
        seen.append("operation")
        return "PRIVATE_RESULT"

    def validate(changes, principal):
        seen.append("validate")
        return validate_single_insert(changes, principal)

    committed = run_guarded_source(
        settings, authorize=authorize, operation=operation, validate=validate
    )
    assert seen == ["authorize", "operation", "validate"]
    assert committed.result == "PRIVATE_RESULT" and "PRIVATE_RESULT" not in repr(committed)
    assert [row["id"] for row in saved(settings)] == ["source"]


def test_guarded_source_rejects_mutating_authorization_and_validation(tmp_path):
    settings = database(tmp_path)
    calls = []

    def authorize_writes(connection):
        connection.execute(t.campaigns.insert().values(id="unauthorized", guild_id="11"))
        return "synthetic-only"

    with pytest.raises(SourceTransactionError, match="Authorization must not mutate"):
        run_guarded_source(
            settings,
            authorize=authorize_writes,
            operation=lambda *_: calls.append("unexpected"),
            validate=validate_single_insert,
        )
    assert not saved(settings) and calls == []
    held = []

    def operation(connection, _principal):
        held.append(connection)
        connection.execute(t.campaigns.insert().values(id="source", guild_id="11"))

    def mutating_validation(changes, principal):
        evidence = validate_single_insert(changes, principal)
        held[0].execute(t.campaigns.update().values(guild_id="22"))
        return evidence

    with pytest.raises(SourceTransactionError, match="Validation changed"):
        run_guarded_source(
            settings,
            authorize=lambda _: "synthetic-only",
            operation=operation,
            validate=mutating_validation,
        )
    assert not saved(settings)
    assert held[0].closed


def test_guarded_source_rolls_back_validation_error_and_caught_implicit_rollback(tmp_path):
    settings = database(tmp_path)

    def operation(connection, _principal):
        connection.execute(t.campaigns.insert().values(id="source", guild_id="11"))

    def reject(_changes, _principal):
        raise ValueError("Unsupported source effects")

    with pytest.raises(ValueError, match="Unsupported source"):
        run_guarded_source(
            settings, authorize=lambda _: "synthetic-only", operation=operation, validate=reject
        )
    assert not saved(settings)

    def rollback_then_continue(connection, principal):
        operation(connection, principal)
        with pytest.raises(sa.exc.IntegrityError):
            connection.exec_driver_sql(
                "INSERT OR ROLLBACK INTO campaigns(id, guild_id) VALUES ('source', '22')"
            )
        # Even if the callback swallows the SQL failure, the wrapper cannot accept
        # missing evidence and must never commit an autocommit escape.
        return "not a successful operation"

    with pytest.raises(CaptureError, match="transaction ended"):
        run_guarded_source(
            settings,
            authorize=lambda _: "synthetic-only",
            operation=rollback_then_continue,
            validate=validate_single_insert,
        )
    assert not saved(settings)


@pytest.mark.parametrize("cleanup_stage", ("connection", "engine"))
def test_postcommit_cleanup_failure_reports_committed_not_retryable(
    tmp_path, monkeypatch, cleanup_stage
):
    settings = database(tmp_path)
    engine = create_database_engine(settings)
    if cleanup_stage == "connection":
        connection = engine.connect()
        original_close = connection.close

        def fail_close():
            original_close()
            raise RuntimeError("synthetic postcommit connection cleanup")

        monkeypatch.setattr(connection, "close", fail_close)
        monkeypatch.setattr(engine, "connect", lambda: connection)
    else:
        original_dispose = engine.dispose

        def fail_dispose():
            original_dispose()
            raise RuntimeError("synthetic postcommit engine cleanup")

        monkeypatch.setattr(engine, "dispose", fail_dispose)
    monkeypatch.setattr(p1_guarded_source, "create_database_engine", lambda _: engine)

    def operation(connection, _principal):
        connection.execute(t.campaigns.insert().values(id="source", guild_id="11"))
        return "PRIVATE_RESULT"

    with pytest.raises(SourceCommittedCleanupError, match="committed successfully.*do not repeat"):
        run_guarded_source(
            settings,
            authorize=lambda _: "synthetic-only",
            operation=operation,
            validate=validate_single_insert,
        )
    # Verify with a separate engine, not the injected failing cleanup object.
    assert [row["id"] for row in saved(settings)] == ["source"]
