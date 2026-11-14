# P1 preparation evidence hardening, 2026-11-10

Preparation-only isolated copy. Bot remains off. No producer is wired, no dispatch,
no safe shelving completion, no canonical actor admission or activation is claimed.

Changed scope:
- `prepare` requires exact canonical preparation evidence in the referenced event's
  `external_effect_preparations` array. An arbitrary existing event no longer
  satisfies provenance binding. Producers still must authenticate original source,
  actor generations, resource ownership and complete cast incidence before committing
  that evidence. Merely constructing matching JSON is not canonical authorization.
- Exact replay also checks stored actor projections and resource linkage. Physical
  destination registry now retains bot and original DM recipient as well as channel.
- SQLite guards reject update, delete and replacement of persisted evidence and its
  referenced event. Actor and resource inserts must match the stored preparation;
  each effect has only its original resource linkage. This is database invariant
  protection, not protection against a database administrator dropping triggers.
- Migration 0017 now contains its original schema definitions instead of importing
  the mutable runtime module. Additive 0018 installs frozen guard SQL. Existing rows
  are neither rewritten nor certified: older incomplete evidence fails closed on
  replay, and populated evidence cannot be downgraded out of protection.

Tests authored: exact source/actor/resource/payload evidence, rollback/idempotency,
physical ownership, update/delete/replace rejection, inconsistent projection insert,
legacy pause preservation, populated downgrade refusal, and historical migration
independence from application schema. Tests NOT RUN by implementation worker; root
owns the minimum smoke. Full regression, independent review and player acceptance
remain pending. Ruff formatting and focused lint passed after fixing an import
spacing issue and long SQL lines. Initial default Python lacked ruff; existing pinned
adapter environment was then used, without installation.

Root command from this copy (PYTHONPATH prevents using another checkout's package):

    PYTHONPATH=src /workspace/scratch/1003c11eb181/harpyengine-p1-adapter-20261109/.venv/bin/python -m pytest -q tests/test_p1_effect_journal.py

The two migration tests cover 0016 -> 0018 upgrade, legacy preservation, refusal to
remove populated evidence, and empty 0018 -> 0016 downgrade. No live DB is used.

Dependencies before producer wiring: canonical source-specific authorization and
transaction origin, complete actual actor/resource generation evidence, admission,
shared drain/restoration and durable runtime producers. This patch only closes the
arbitrary-event and mutable journal acceptance paths within preparation storage.

## Independent review corrections

Root ran the initial six focused tests: 6 passed in 0.62s. Review then found an
occupied-rowid replacement bypass and semantic JSON duplicate path. A bounded
stdlib SQLite 3.53.1 demonstration confirmed the rowid bypass with recursive_triggers
OFF, then confirmed an occupied-rowid insert guard blocks it. Runtime and pending
0018 migration now include that guard for all journal tables and referenced events.
Parsed actor identity now enforces duplicate prevention and token consistency across
relations. Canonical first-token derivation remains the service boundary, not an
SQL authorization claim. Replay now checks event_seq, operation, payload_digest,
state, revision and schema version in addition to semantic keys/body/projections.
Three regressions authored for these review findings; root execution pending.
No packaging performed pending re-review. Updated docs/design/P1_EFFECT_PREPARATION.md
explicitly preserves evidence-binding versus authenticated-provenance limits.

Second review correction: root ran the revised nine focused tests (9 passed, 0.67s).
Review then identified the remaining events command_key/event_index unique-conflict
route for multirow OR REPLACE. Runtime and frozen pending migration now also guard
(campaign_id, command_key, event_index), alongside id, campaign/seq and rowid.
The exact two-row replacement regression is authored against both metadata-created
and migration-created schemas, with recursive triggers OFF and no explicit rowid.
These two new test cases await root execution; targeted Ruff passes. Package remains
unbuilt until independent re-review.


Final root evidence: the two exact multirow regression cases passed in 0.48s on
the final code, including a schema built by migration 0018. Earlier nine focused
cases passed in 0.67s, and the separate database migration node passed in 0.54s
before the final source unique-key correction. Do not represent this as a single
11-test final run or a full regression. Independent static re-review compared the
runtime/frozen guard blocks and found them identical, closed the reported blockers,
and found no further concrete blocker within preparation-only scope. It ran no
tests. Producer authentication, dispatch, shelving and human acceptance stay pending.
