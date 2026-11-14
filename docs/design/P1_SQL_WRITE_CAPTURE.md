# Bounded SQL mutation capture prerequisite

Unused implementation. No source transaction, producer, worker, availability or
shelving activation is wired. The collector is evidence for a future final
transaction validator, not that validator, an actor ownership classifier, or
permission to commit. Existing shelving and journal reserve rejection are unchanged.

## Mechanism

`services/p1_write_capture.py::capture_writes` installs connection-local TEMP
triggers on all 43 modeled application tables. SQL-only INSERT/UPDATE/DELETE,
primary-key changes, nested trigger effects and SQLite implicit replacement deletes
produce ordered before/after keys and complete before/after row JSON. Caller
statements are not parsed to infer writes. Rollback also rolls back captured rows.
Captured identifiers/rows are private; Change repr excludes them, and the reader
closes at context exit. TEMP storage is ephemeral, not a promise of encrypted or
memory-only storage. No reason text or actor facts are inferred from arbitrary JSON.

Actual table/column/key names must match the runtime schema inventory; missing or
unknown application tables/columns/keys reject capture. Alembic bookkeeping is not
a gameplay table and cannot be written while capturing. Future typed actor policies
must separately register the semantic meaning of every mutable field. Generic
capture of a new modeled field is not approval to mutate it.

The source connection must already have a real SQLite transaction, foreign keys ON,
recursive triggers ON, and writable_schema OFF. Recursive triggers are essential
for implicit REPLACE deletes. Current runtime defaults have recursive triggers OFF,
so this module intentionally cannot be silently enabled on those connections.
It does not change connection defaults or create a durable migration.

An exclusive SQLite authorizer rejects transaction/savepoint control, schema/PRAGMA
changes, attachment changes and direct capture-log writes. All nested savepoint
control is currently rejected; this avoids treating release of an outer savepoint
as safe. Existing producers such as journal preparation that use begin_nested need
a separate managed-savepoint integration before they can run under this collector.

The caller must explicitly assert exclusive authorizer ownership. Python sqlite3
cannot retrieve/restore an existing authorizer. This module must never overwrite a
separate authorization policy; future application integration needs a managed owner
at connection construction. A caller holding arbitrary raw Python/SQLite handles
can replace the authorizer: this is a cooperative application boundary, not database
administrator isolation. No exception is added to the confirmation/access policy.

Row count and before/after row-payload byte limits abort the offending SQL
statement. Defaults are 2,048 changes and 4 MiB of row-payload JSON. The max_bytes
budget excludes duplicated primary-key JSON, table/operation strings, SQLite log
metadata and Python copies returned by changes(). It is not a total storage or
memory cap. These limits are not a measured performance guarantee. Sum/count work
is bounded by the row limit but not constant cost. Private before/after row data
is deleted during cleanup; the caller owns evidence already read into memory and
must not log it.

## Remaining integration requirements

Capture covers only mutations while its context is open. It cannot prove that a
caller made no prior writes in an already-open transaction. The future canonical
transaction wrapper must install it at source transaction entry, prohibit early
commits, run typed final validation inside the context, and roll back if validation
fails. Do not treat calling this helper after writes as whole-transaction evidence.

Final validation must authenticate the actual command principal and source, resolve
current original actors and availability generations, classify all canonical and
operational changes, preserve absent choices/receipts/obligations, and reject unknown
or affected unauthorized changes. Actor/resource admission, durable availability,
worker intent/permit/drain/reconciliation, parking and rejoin remain unimplemented.
A captured write list does not prove any of these. No freeze may activate from it.

## Candidate and verification

Candidate: harpyengine-p1-write-capture-20261110, copied from v33 review UI after
verifying its three packaged output hashes. The prior source already reconciled
v30 preflight and the separate v32 Processor layer by hashes. No existing source
file or migration was modified. Two new Python files and this document are owned.

Worker scoped Ruff check/format and mypy --follow-imports=silent on the new service
passed. Worker did not run pytest. Root minimum:

    PYTHONPATH=src /workspace/scratch/1003c11eb181/harpyengine-p1-adapter-20261109/.venv/bin/python -m pytest -q tests/test_p1_write_capture.py

Three authored cases: actual SQL insert/update/rowid replacement and source rollback;
transaction/schema/log-tamper rejection with subsequent connection reuse; and unsafe
default/unknown-table rejection plus bounded-statement rollback. Independent review,
root execution, final global checks and live/user acceptance remain pending. No bot,
deployment, merge, publication or access-restriction workaround.

Reviewer clarification: max_bytes is a row-payload budget only, as detailed above.
This correction changed documentation only; tested Python files were not edited.

## Implicit rollback correction

Review identified that INSERT OR ROLLBACK can end the source transaction and remove
its TEMP triggers without an explicit transaction-control statement. The collector
now checks actual SQLite transaction liveness before every SQLAlchemy cursor
execution, including cached statements, and inside the SQLite authorizer for raw
statement preparation. A lost transaction invalidates capture immediately, denies
subsequent work rather than allowing autocommit, and still rejects context exit.
Cleanup releases the execution hook and authorizer without committing anything.

A fourth focused regression primes a WITH-prefixed raw insertion, triggers an
implicit conflict rollback, catches it, then attempts both SQLAlchemy and raw cached
insertions. Both must reject, captured evidence must be unavailable, and a reopened
connection must find no committed rows. This code change needs root rerun/review;
prior test results do not cover the correction. Scoped Ruff and mypy pass. No
package has been created while this finding is pending verification.
