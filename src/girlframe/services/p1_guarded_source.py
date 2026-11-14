"""Guarded source transaction owner; callback policy is not shelving authorization.

Private intake and explicit Pilot enrollment use this owner. Callbacks must be
trusted, synchronous and local-only. Do not perform network/file effects or
replace SQL hooks inside them. No gameplay freeze or dispatch permit is implied."""

from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import Connection

from girlframe.config import Settings
from girlframe.database.connection import create_database_engine
from girlframe.services.p1_write_capture import Change, capture_writes


class SourceTransactionError(RuntimeError):
    """Non-private lifecycle violation; no permission or successful commit inferred."""


class CommitOutcomeUnknown(SourceTransactionError):
    """Commit did not return successfully; inspect durable state before any retry."""


class SourceCommittedCleanupError(SourceTransactionError):
    """Commit returned successfully, but cleanup failed. Never repeat the operation."""


@dataclass(frozen=True)
class CommittedSource[Result, Evidence]:
    result: Result = field(repr=False)
    evidence: Evidence = field(repr=False)


def run_guarded_source[Principal, Result, Evidence](
    settings: Settings,
    *,
    authorize: Callable[[Connection], Principal],
    operation: Callable[[Connection, Principal], Result],
    validate: Callable[[tuple[Change, ...], Principal], Evidence],
) -> CommittedSource[Result, Evidence]:
    """Own one fresh connection from BEGIN IMMEDIATE through final commit.

    Authorization must reread current canonical authority, not deserialize a
    caller's claimed principal. Validation must authenticate/classify the complete
    actual write set. These required callbacks have NO permissive default; this
    wrapper cannot prove an arbitrary callback correct. In particular the current
    Heat comparator alone is not a complete gameplay source policy.

    Fresh engine/connection ownership avoids silently replacing another pooled
    connection's SQLite authorizer. No prior application writes are possible before
    capture. Raw/SQLAlchemy nested transaction controls remain rejected; only
    owned source_savepoint scopes may nest under capture. This changes no shared
    engine defaults and does not migrate a database.
    """
    engine = create_database_engine(settings)
    commit_attempted = False
    commit_succeeded = False
    committed: CommittedSource[Result, Evidence] | None = None
    failure: BaseException | None = None
    try:
        with engine.connect() as connection:
            # This fresh connection is exclusively ours. No source callback has run.
            connection.exec_driver_sql("PRAGMA recursive_triggers=ON")
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            transaction = connection.get_transaction()
            if transaction is None:
                raise SourceTransactionError("Source transaction failed to begin")
            try:
                with capture_writes(connection, exclusive_authorizer=True) as capture:
                    principal = authorize(connection)
                    if capture.changes():
                        raise SourceTransactionError("Authorization must not mutate source state")
                    result = operation(connection, principal)
                    changes = capture.changes()
                    evidence = validate(changes, principal)
                    # A validator may retain the operation's connection by closure.
                    # Actual new mutations, even changed then reverted, cannot hide.
                    if capture.changes() != changes:
                        raise SourceTransactionError("Validation changed its own source evidence")
                    if connection.get_transaction() is not transaction or not transaction.is_active:
                        raise SourceTransactionError("Source transaction ownership changed")
                # No user callback runs after validation/capture cleanup and before
                # commit. The wrapper, never the operation, owns this boundary.
                commit_attempted = True
                connection.commit()
                commit_succeeded = True
            except BaseException as error:
                if commit_attempted:
                    # Cleanup failure must not hide the uncertain commit boundary.
                    try:
                        connection.rollback()
                    except BaseException:
                        pass
                    raise CommitOutcomeUnknown(
                        "Source commit did not return successfully; inspect before retrying"
                    ) from error
                connection.rollback()
                raise
            committed = CommittedSource(result=result, evidence=evidence)
    except BaseException as error:
        failure = error
    finally:
        try:
            engine.dispose()
        except BaseException as error:
            if failure is None:
                failure = error
    # Context-manager exit and engine disposal are part of outcome reporting too.
    # Neither can turn durable effects into an apparently retryable ordinary error.
    if failure is not None:
        if commit_succeeded:
            raise SourceCommittedCleanupError(
                "Source committed successfully but cleanup failed; do not repeat the operation"
            ) from failure
        if commit_attempted and not isinstance(failure, CommitOutcomeUnknown):
            raise CommitOutcomeUnknown(
                "Source commit outcome is uncertain; inspect before retrying"
            ) from failure
        raise failure
    assert committed is not None
    return committed
