"""Unused bounded SQL write evidence collector, not a freeze or admission policy.

Requires exclusive ownership of SQLite's connection authorizer. Current runtime
transactions do not install it. Returned rows are private and must never be logged.
"""

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t


class CaptureError(RuntimeError):
    """Non-private failure to establish complete bounded mutation evidence."""


def _quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _json(columns: list[str], alias: str) -> str:
    values = ", ".join(
        "'" + name.replace("'", "''") + "', " + alias + "." + _quote(name) for name in columns
    )
    return "json_object(" + values + ")"


@dataclass(frozen=True)
class Change:
    table: str
    operation: str
    before_key: str | None = field(repr=False)
    after_key: str | None = field(repr=False)
    before_row: str | None = field(repr=False)
    after_row: str | None = field(repr=False)


class WriteCapture:
    """Only a private evidence reader. No dispatch/availability authorization exists."""

    def __init__(self, connection: Connection, table: str):
        self._connection = connection
        self._table = table
        self._open = True
        self._savepoints: list[str] = []
        self._step: Callable[[], AbstractContextManager[None]] | None = None

    def changes(self) -> tuple[Change, ...]:
        if not self._open:
            raise CaptureError("Write capture is closed; resolve evidence inside its transaction")
        if self._savepoints:
            raise CaptureError("Finish every managed source step before validating write evidence")
        rows = self._connection.exec_driver_sql(
            f"SELECT table_name, operation, before_key, after_key, before_row, after_row "
            f"FROM temp.{_quote(self._table)} ORDER BY sequence"
        )
        return tuple(Change(*row) for row in rows)


@contextmanager
def source_savepoint(connection: Connection) -> Iterator[None]:
    """Atomic local step; captured writes roll back with the same SQLite savepoint.

    Outside capture, preserve SQLAlchemy's existing nested transaction behavior.
    Inside capture, only the owner's exact one-shot controls are admitted. This
    is cooperative transaction plumbing, never source or dispatch authorization.
    """
    reader = connection.info.get("p1_write_capture")
    if reader is None:
        with connection.begin_nested():
            yield
    elif (
        isinstance(reader, WriteCapture)
        and reader._connection is connection
        and reader._open
        and reader._step is not None
    ):
        with reader._step():
            yield
    else:
        raise CaptureError("Recover the active source capture before opening an atomic step")


def _schema(connection: Connection) -> dict[str, tuple[list[str], list[str]]]:
    inspector = sa.inspect(connection)
    expected = set(t.metadata.tables)
    actual = set(inspector.get_table_names())
    # Alembic's bookkeeping is never a gameplay writer.
    if actual - {"alembic_version"} != expected:
        raise CaptureError("Unknown or missing application table; capture is unavailable")
    result = {}
    for name, table in t.metadata.tables.items():
        columns = list(table.columns.keys())
        keys = [column.name for column in table.primary_key.columns]
        actual_columns = inspector.get_columns(name)
        if (
            # Historical ALTER TABLE migrations append columns; capture uses
            # explicit names, so physical ordinal position carries no authority.
            {column["name"] for column in actual_columns} != set(columns)
            or len(actual_columns) != len(columns)
            or inspector.get_pk_constraint(name)["constrained_columns"] != keys
            or not keys
            or any(isinstance(column["type"], sa.LargeBinary) for column in actual_columns)
        ):
            raise CaptureError("Unregistered column or key shape; capture is unavailable")
        result[name] = (columns, keys)
    return result


@contextmanager
def capture_writes(
    connection: Connection,
    *,
    exclusive_authorizer: bool = False,
    max_changes: int = 2048,
    max_bytes: int = 4 * 1024 * 1024,
) -> Iterator[WriteCapture]:
    """Collect actual SQL mutations inside one existing SQLite transaction.

    Explicit authorizer ownership is mandatory: sqlite3 cannot retrieve/restore a
    pre-existing callback. Do not use alongside any other connection authorizer.
    Current application defaults have recursive_triggers OFF and are rejected;
    integration must establish ON before entering the source transaction.
    Raw transaction/savepoint control remains denied. source_savepoint admits
    only owned one-shot savepoint controls; both row data and its temporary log
    are transactional. A rolled-back atomic step therefore leaves neither.
    Sources must finish all managed steps before validating their final evidence.
    """
    raw = connection.connection.driver_connection
    if (
        not exclusive_authorizer
        or not isinstance(raw, sqlite3.Connection)
        or not raw.in_transaction
        or connection.info.get("p1_write_capture")
    ):
        raise CaptureError("Capture requires an exclusive authorizer and open SQLite transaction")
    if type(max_changes) is not int or not 1 <= max_changes <= 10000:
        raise CaptureError("Invalid capture row bound")
    if type(max_bytes) is not int or not 1 <= max_bytes <= 64 * 1024 * 1024:
        raise CaptureError("Invalid capture byte bound")
    if (
        connection.exec_driver_sql("PRAGMA recursive_triggers").scalar() != 1
        or connection.exec_driver_sql("PRAGMA foreign_keys").scalar() != 1
        or connection.exec_driver_sql("PRAGMA writable_schema").scalar() != 0
    ):
        raise CaptureError("Capture requires recursive triggers, foreign keys and protected schema")
    schema = _schema(connection)
    suffix = uuid4().hex
    log = "p1_capture_" + suffix
    triggers: set[str] = set()
    reader = WriteCapture(connection, log)
    connection.info["p1_write_capture"] = reader
    authorizer_installed = False
    liveness_installed = False

    def require_live_transaction(*_args: object) -> None:
        # Runs before every SQLAlchemy execution, including cached statements.
        # Conflict clauses can roll back without an explicit ROLLBACK statement.
        if not reader._open or not raw.in_transaction:
            reader._open = False
            raise CaptureError("Source transaction ended; write capture is invalid")

    try:
        connection.exec_driver_sql(
            f"CREATE TEMP TABLE {_quote(log)} (sequence INTEGER PRIMARY KEY, "
            "table_name TEXT NOT NULL, operation TEXT NOT NULL, before_key TEXT, "
            "after_key TEXT, before_row TEXT, after_row TEXT, bytes INTEGER NOT NULL)"
        )
        for table, (columns, keys) in schema.items():
            for operation in ("INSERT", "UPDATE", "DELETE"):
                name = f"{log}_{len(triggers)}"
                old_key = "NULL" if operation == "INSERT" else _json(keys, "OLD")
                new_key = "NULL" if operation == "DELETE" else _json(keys, "NEW")
                old = "NULL" if operation == "INSERT" else _json(columns, "OLD")
                new = "NULL" if operation == "DELETE" else _json(columns, "NEW")
                size = (
                    f"coalesce(length(CAST({old} AS BLOB)), 0) + "
                    f"coalesce(length(CAST({new} AS BLOB)), 0)"
                )
                connection.exec_driver_sql(
                    f"CREATE TEMP TRIGGER {_quote(name)} AFTER {operation} ON main.{_quote(table)} "
                    "BEGIN "
                    f"SELECT CASE WHEN (SELECT count(*) FROM {_quote(log)}) >= {max_changes} "
                    f"OR (SELECT coalesce(sum(bytes), 0) FROM {_quote(log)}) "
                    f"+ {size} > {max_bytes} "
                    "THEN RAISE(ABORT, 'SQL write capture limit exceeded') END; "
                    f"INSERT INTO {_quote(log)} (table_name, operation, before_key, after_key, "
                    f"before_row, after_row, bytes) VALUES ('{table}', '{operation.lower()}', "
                    f"{old_key}, {new_key}, {old}, {new}, {size}); END"
                )
                triggers.add(name)

        denied = {
            sqlite3.SQLITE_TRANSACTION,
            sqlite3.SQLITE_SAVEPOINT,
            sqlite3.SQLITE_PRAGMA,
            sqlite3.SQLITE_ATTACH,
            sqlite3.SQLITE_DETACH,
            sqlite3.SQLITE_ALTER_TABLE,
            sqlite3.SQLITE_CREATE_INDEX,
            sqlite3.SQLITE_CREATE_TABLE,
            sqlite3.SQLITE_CREATE_TRIGGER,
            sqlite3.SQLITE_CREATE_VIEW,
            sqlite3.SQLITE_CREATE_TEMP_INDEX,
            sqlite3.SQLITE_CREATE_TEMP_TABLE,
            sqlite3.SQLITE_CREATE_TEMP_TRIGGER,
            sqlite3.SQLITE_CREATE_TEMP_VIEW,
            sqlite3.SQLITE_CREATE_VTABLE,
            sqlite3.SQLITE_DROP_INDEX,
            sqlite3.SQLITE_DROP_TABLE,
            sqlite3.SQLITE_DROP_TRIGGER,
            sqlite3.SQLITE_DROP_VIEW,
            sqlite3.SQLITE_DROP_TEMP_INDEX,
            sqlite3.SQLITE_DROP_TEMP_TABLE,
            sqlite3.SQLITE_DROP_TEMP_TRIGGER,
            sqlite3.SQLITE_DROP_TEMP_VIEW,
            sqlite3.SQLITE_DROP_VTABLE,
            sqlite3.SQLITE_REINDEX,
            sqlite3.SQLITE_ANALYZE,
        }

        expected_control: tuple[str, str] | None = None

        def authorize(
            action: int,
            target: str | None,
            _column: str | None,
            database: str | None,
            source: str | None,
        ) -> int:
            nonlocal expected_control
            # Also protect newly prepared raw DBAPI statements, which do not pass
            # through the SQLAlchemy execution hook. Never permit autocommit work.
            if not reader._open or not raw.in_transaction:
                reader._open = False
                return sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_SAVEPOINT and expected_control == (target, _column):
                expected_control = None
                return sqlite3.SQLITE_OK
            if action in denied:
                return sqlite3.SQLITE_DENY
            if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE):
                if database == "main" and target in schema:
                    return sqlite3.SQLITE_OK
                if (
                    database == "temp"
                    and target == log
                    and source in triggers
                    and action == sqlite3.SQLITE_INSERT
                ):
                    return sqlite3.SQLITE_OK
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        def control(operation: str, name: str) -> None:
            nonlocal expected_control
            if not reader._open or not raw.in_transaction or expected_control is not None:
                reader._open = False
                raise CaptureError("Managed source step lost its original transaction")
            verbs = {
                "BEGIN": "SAVEPOINT",
                "ROLLBACK": "ROLLBACK TO SAVEPOINT",
                "RELEASE": "RELEASE SAVEPOINT",
            }
            expected_control = (operation, name)
            try:
                # Invalidate prior authorized prepared statements before and after
                # each exact control. No user code runs in the one-shot window.
                raw.set_authorizer(authorize)
                raw.execute(verbs[operation] + " " + _quote(name))
                if expected_control is not None:
                    raise CaptureError("Managed source control lacked authorizer evidence")
            except BaseException:
                reader._open = False
                raise
            finally:
                expected_control = None
                try:
                    raw.set_authorizer(authorize)
                except BaseException:
                    reader._open = False
                    raise

        @contextmanager
        def managed_step() -> Iterator[None]:
            name = "p1_step_" + uuid4().hex
            control("BEGIN", name)
            reader._savepoints.append(name)
            try:
                yield
            except BaseException:
                if not reader._savepoints or reader._savepoints[-1] != name:
                    reader._open = False
                    raise CaptureError(
                        "Managed source steps must close in original order"
                    ) from None
                control("ROLLBACK", name)
                control("RELEASE", name)
                reader._savepoints.pop()
                raise
            else:
                if not reader._savepoints or reader._savepoints[-1] != name:
                    reader._open = False
                    raise CaptureError("Managed source steps must close in original order")
                control("RELEASE", name)
                reader._savepoints.pop()

        reader._step = managed_step
        raw.set_authorizer(authorize)
        authorizer_installed = True
        sa.event.listen(connection, "before_cursor_execute", require_live_transaction)
        liveness_installed = True
        yield reader
        if not reader._open or not raw.in_transaction or reader._savepoints:
            raise CaptureError(
                "Source transaction or managed step ended without complete validation"
            )
    finally:
        reader._open = False
        reader._step = None
        if liveness_installed:
            sa.event.remove(connection, "before_cursor_execute", require_live_transaction)
        if authorizer_installed:
            raw.set_authorizer(None)
        # Never commit, roll back, or expose private row contents during cleanup.
        for name in triggers:
            connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS temp.{_quote(name)}")
        connection.exec_driver_sql(f"DROP TABLE IF EXISTS temp.{_quote(log)}")
        connection.info.pop("p1_write_capture", None)
