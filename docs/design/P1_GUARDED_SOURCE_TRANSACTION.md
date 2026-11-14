# Dedicated guarded source transaction owner

Unused preparation helper. No existing source, worker, UI or availability transition
calls it. This is transaction machinery, not actor admission, safe shelving, consent,
source authentication or permission to run a gameplay command. Shelving activation
and journal reservation remain unavailable.

## Mechanism

`run_guarded_source` opens its own fresh engine/connection through the existing local
SQLite factory. It sets recursive trigger coverage on that connection before BEGIN
IMMEDIATE, then installs the v37 collector before any source callback can write.
A pooled connection or pre-existing authorizer is never borrowed. Existing shared
engines and their defaults are unchanged; the database is not migrated.

Required trusted callbacks provide current authorization, source operation and final
validation. There is no permissive default. Authorization must read current storage
and must not mutate it. The operation receives only the newly resolved principal
and the guarded connection. Validation receives the exact captured write tuple and
principal. Captured writes are compared again afterward, so a validator cannot use
a retained connection to change or revert evidence unnoticed. The original managed
transaction must remain live and owned by the wrapper. No caller callback runs
between final validation/capture cleanup and commit.

Operation/authorization/validation failures roll back before returning. Implicit
conflict rollback remains caught by collector liveness checks; a callback swallowing
the SQL error cannot promote the empty/missing evidence to a commit. Early transaction
and raw/SQLAlchemy nested savepoint control remain rejected. Owned source_savepoint
scopes now support nesting under capture; see P1_MANAGED_SOURCE_SAVEPOINTS.md.
Successful output is returned only
after commit returns successfully, with private result/evidence excluded from repr.
A commit exception is reported as CommitOutcomeUnknown, never a promise of rollback
or permission to retry. There is no retry loop.

## Trust and remaining gaps

Callbacks are internal, synchronous, local-only code. They must not reset SQLite or
SQLAlchemy hooks, alter raw connection ownership, create concurrent users, or perform
network/file effects. The wrapper is a cooperative application boundary, not isolation
from arbitrary privileged Python code. A caller can supply a useless validator; this
module does not authenticate the validator itself. Concrete producer integration must
supply independently reviewed source-specific authorization and classification.

The narrow v37 Heat comparator is still not a complete gameplay source policy:
command/event/idempotency/receipt/outbox effects need precise authorized adapters.
No actual protected actor availability record, generation, source choice or consent is
created by this helper. Actor/resource incidence, worker permit/drain/reconciliation
and parked-source/rejoin remain required. The managed-savepoint addon now supports
the existing journal preparation step, not arbitrary producer transaction controls.
No freeze may be enabled based on transaction mechanics alone.

A fresh connection per call is deliberately conservative; no throughput/constant-cost
claim is made. The collector's bound covers row-payload bytes, not total memory/storage.
The fresh engine must use an existing migrated local database. Unknown schema rejects
before application callbacks run. No production database or remote service was used.

## Reconstruction and checks

The restored filesystem held only an older revision5 archive and lacked the latest
source directories. The exact cumulative Space identity was materialized through its
supported route as version37; archive SHA-256:
07e3cde148126d5a53e42840a9aa2546f395cef286a418625c475b697abdb50a.
All packaged checksums were verified. A new isolated tree was reconstructed from the
available published b265003 Git object, the portable selected-v33 combined patch,
v35 collector and v37 canonical correction. All 1,482 selected-source hashes and
every incremental input/output hash matched. Historical combined patch has two
trailing-whitespace warnings; exact bytes were preserved, not reformatted.

Candidate: harpyengine-p1-guarded-source-20261110. Three new files only: service,
focused tests and this design. No existing runtime/migration modified. Worker Ruff
lint/format and targeted mypy pass; worker did not run pytest. Root minimum:

    PYTHONPATH=src /workspace/scratch/1003c11eb181/harpyengine-p1-adapter-20261109/.venv/bin/python -m pytest -q tests/test_p1_guarded_source.py

Three authored cases cover capture from first write and successful synthetic commit,
mutating authorization/validation refusal, validation-error rollback and swallowed
implicit-rollback failure. Callbacks are explicitly synthetic; these cases do not
prove actual gameplay source authentication or a complete actor freeze. Root tests,
independent review, full exact-candidate gates and human acceptance remain pending.
No bot, deployment, merge, publication, broad regression or denied-access workaround.

## Post-commit cleanup outcome correction

Independent review identified that connection-context exit or engine disposal could
raise after a successful commit and escape as an ordinary failure. Outcome handling
now surrounds the entire connection context and final disposal. A returned commit
followed by cleanup failure raises SourceCommittedCleanupError, explicitly stating
that the operation committed and must not be repeated. A commit attempt that did
not return successfully remains CommitOutcomeUnknown even if cleanup also fails.
No cleanup error is interpreted as proof of rollback.

Two injected regressions cover post-commit connection close and engine disposal
failures, each confirming durable effects through a separate engine. They join the
three original synthetic mechanics cases. Revised five-case execution and independent
re-review are pending; earlier checks do not cover this correction. Scoped Ruff and
targeted mypy pass. No package created while verification remains pending.
