# Managed source savepoints (preparation integration)

Baseline is the verified v38 guarded-source snapshot. This slice lets the existing preparation journal run an atomic step inside the guarded transaction. It does not admit a gameplay source, authenticate actors/generations, grant dispatch, activate shelving or freeze anyone.

## Concrete incompatibility

Journal `prepare` used SQLAlchemy `begin_nested()` to prevent a caught conflict from leaving half an effect. The capture authorizer denied all SQLITE_SAVEPOINT actions. Consequently that existing journal could not run inside the guarded wrapper at all. Removing the denial globally would let a producer manipulate transaction scopes and evidence.

## Selected boundary

`source_savepoint(connection)` preserves normal SQLAlchemy nested behavior outside capture. Inside capture it delegates to the actual connection's live collector. The collector generates a fresh unpredictable savepoint name, admits only its exact next BEGIN/ROLLBACK/RELEASE authorization callback, consumes that permission once, and resets the authorizer before and after the control to invalidate prepared-statement authorization. No user callback runs in that narrow window. Caller-issued transaction controls and savepoints remain denied, including reusing previously authorized text.

Managed scopes close in LIFO order. Capture evidence cannot be read as final while a scope is open. A failed control, lost outer transaction, wrong scope ordering or authorizer-reset failure invalidates capture. The owning guarded wrapper must roll back the outer transaction on failure; no retry or successful commit is inferred. The wrapper API and commit-uncertainty behavior are unchanged.

The temporary evidence log and application rows share the SAME SQLite savepoint. Rolling back an atomic step removes its rows and its corresponding evidence; earlier outer work survives. Released work remains in evidence. Ordinary update-then-revert remains two observed mutations, not erased history. Bounds apply to the retained transactional evidence, not cumulative CPU/work across aborted attempts.

This remains cooperative code, not a sandbox against hostile Python callbacks. Do not replace authorizers/hooks, use side connections or external effects in a local step. The wrapper owns the complete outer transaction. A standalone collector caller remains responsible for rolling back on capture errors. Current source-specific validation, real worker permits/drain, actor availability, source parking and runtime publication remain separate.

## Authored minimum

`tests/test_p1_managed_savepoint.py` contains four focused cases:
1. Real event-attested journal preparation inside the guarded source; synthetic failure after partial journal insertion rolls back all attempted journal rows/evidence, then actual retry/replay yields one prepared effect and a complete validated write set.
2. Nested managed rollback removes only the inner step; earlier and later outer writes remain, as do update/revert observations.
3. Raw transaction/savepoint controls, SQLAlchemy begin_nested and exact cached replay of previously allowed control SQL remain denied. Final evidence is refused inside an active step.
4. Implicit outer ROLLBACK inside a step poisons capture; catching the exception cannot authorize validation or commit.

Synthetic callbacks assert shapes only; they are not canonical source admission. Worker does not run pytest. Root owns execution and final evidence. No existing broad suite rerun is proposed.

## Final scoped evidence

Root reports the four authored focused cases passed: **4 passed in 0.79s**.
Independent transaction/security review reported no blocker and requested clearer
nested-scope documentation. After that run, only the guarded-wrapper docstring
and design prose were clarified: raw/SQLAlchemy nesting remains denied, while
owned source_savepoint scopes support nesting. An AST comparison with docstrings
removed confirmed identical executable wrapper structure. No executable source or
test logic changed after the passing run. Final four-Python-file Ruff lint/format
passed. Worker ran no pytest. Full/global, source admission, runtime, worker and
human gates remain pending.
