# M1 persistence and ledger acceptance

**Status: offline gates PASS; Gateway and registry PASS; new human dice/safety smoke PENDING.**
**Date:** 2026-11-02 (America/Chicago). **Branch:** `codex/m1-ledger`.
**Implementation:** `bced5ab` (the implementation parent of the final evidence commit).

M0 was accepted by the owner. This continues M1 only. Full M1 acceptance remains
pending the new human Discord smoke; no M2 work, official Plays or AI were started.
Earlier evidence is retained in [M1_READ_ONLY_ACCEPTANCE.md](M1_READ_ONLY_ACCEPTANCE.md),
[M1_SERVER_ONBOARDING.md](M1_SERVER_ONBOARDING.md) and
[M1_CHARACTER_TAGS.md](M1_CHARACTER_TAGS.md). Their counts describe earlier phases.

## Implemented result

The guild bot now has campaign create/join/status, saved Girl drafts and sheets,
raw OS-backed 2d6, receipt lookup, filtered ledger pagination, persistent OOC pause/
self-resume, and a transactional public-delivery outbox. `/girl create` opens the
existing dropdown wizard. The original `/campaign_status` keeps its restricted
approved audience and now returns stored M1 status; it does not report a competing
legacy-engine turn counter. `/campaign status` is available to joined members.

Raw rolls validate owner membership, expected campaign revision, pause and own saved
draft before RNG. Each commits one immutable receipt, `dice.rolled` index 0 and
`dice.recorded` index 1, the saved command outcome and optional outbox atomically.
Repeat interaction keys return the same result after restart with zero new RNG;
changed semantic payload conflicts. Expected revision is a first-execution
precondition excluded from the ledger semantic hash. Draft wizard revision behavior
is retained. A stale new command performs no RNG or state changes.

Rolls are private by default. Only `publish:true` queues a receipt to the known
managed ledger. Private sheets/receipts do not gain an administrator override.
Event pages select explicit fields after server-side campaign/visibility filtering;
private notes/snapshots and generic payload bodies are never serialized there.
Safety pause is per participant, requires no reason and bypasses the ordinary UI
throttle. A pause wins over unrelated revision races; resume clears only the caller.
Committed receipt replay still works during a pause.

Delivery uses durable claim tokens, 120-second leases, backoff and stable nonces.
On retry, optional Read Message History permits bounded author/receipt reconciliation
in the dedicated ledger only. Without it, external duplicates are possible. Tests
prove one receipt and unchanged game events even when two Discord posts occur.
No externally exactly-once delivery claim is made.

Local tools provide WAL-consistent private backup, verified restore to a new file,
public-only export, latest-snapshot character rebuild, and new-file synthetic seed.
Migration 0003 adds principal registry, snapshots, receipts, safety and outbox while
preserving existing data. UPDATE/DELETE triggers protect journal, receipts and draft
snapshots. Pre-0003 drafts receive a current-revision baseline with null event source;
missing old revisions are not fabricated. Rebuild never regenerates dice.

## Evidence

Reproducible commands and safe outputs: [M1_LEDGER_VALIDATION.txt](M1_LEDGER_VALIDATION.txt).
Original M1-001–012 mappings: [m1_ledger.json](../docs/acceptance/m1_ledger.json).
Design decisions/limits: [M1_LEDGER.md](../docs/M1_LEDGER.md).
Work order: [M1D_ENGINE_LEDGER.md](../docs/work_orders/M1D_ENGINE_LEDGER.md).

| Check | Actual outcome |
|---|---|
| Locked installation | Passed; no dependency/lock changes |
| Offline tests | **137 passed, 0 failed/skipped/xfailed** |
| Ruff lint / format | Passed; 76 Python files formatted |
| Strict mypy | Passed; 42 application source files |
| Fresh migration / repeat / metadata check / downgrade | Passed on disposable database |
| Populated 0002 → 0003 migration | Passed; baseline snapshots and principals backfilled |
| Concurrency and retries | One winning roll; stale loser samples no dice; restart retries use original receipt |
| Both delivery crash points | Passed with reconciliation; duplicate-post fallback preserves one receipt |
| Private fields / two campaigns / revoked members | Passed with synthetic canaries and IDs |
| Snapshot rebuild / WAL backup / restore / export / seed | Passed on synthetic databases |
| Original planning validator | Passed: 34 required files, 86 planned cases, 4 schemas, 4 fixtures |
| Planning manifest | 40/40 original entries preserved |
| Publishable file scan | 0 findings; limited scanner, not a security certification |
| Wheel / source distribution | Built and inspected; no PDF, DB, credentials, var/cache/venv or private references |
| Configured pilot migration | Private backup retained; existing table counts and draft bytes preserved |
| Existing pilot records | 1 campaign, 1 member, 1 draft, 10 setup resources, 2 roles, 1 tag job, 29 audit events preserved during migration |
| Migrated pilot additions | 1 baseline snapshot; 0 rolls at migration completion |
| Gateway | READY observed with migration 0003 |
| Discord command readback | Exactly 11 guild-scoped roots, expected nested campaign/roll/safety commands, zero global commands |
| Human new-command smoke | Requested; **PENDING**, not counted as passed |
| Recovered private engine | **120/120** original template file hashes unchanged |
| GitHub visibility | Observed PUBLIC; owner explicitly chose to retain public visibility and push sanitized bot source only |
| Remote CI | Configured; result not observed |

Original M1-007's “one event” is interpreted as one `dice.rolled` event, plus the
separate indexed `dice.recorded` event. This preserves the handoff's multi-event
invariant; the historical catalogue itself remains unchanged. Its 86 planned cases
are not all claimed executed. The private engine's earlier 66 tests are a separate
suite, not part of these 137 bot tests.

## Diagnosed failures and limits

Initial existing tests had three expected-surface failures (old table count, command
set and CLI mode). Assertions were updated for the new migration/routes; final
suite passes. The initial non-escalated build could not reach the package proxy;
building through supported command escalation succeeded without changing pins or
TLS. A build-cache inclusion warning was checked against artifact contents: cache
and private directories were absent. An artifact inspection initially tried to open
the build directory's `.gitignore` as a tarball; narrowing it to actual distributions
resolved that inspection error. No application error was hidden by these corrections.

The prior session bot was not running when checked. A new process was started on
the existing saved policy after backup/migration; processes are temporary session
hosting and do not survive environment restoration. No environment configuration
was published. Human smoke is distinct from REST registration and offline testing.
No live forced-crash, long-duration hosting, second-account private denial or normal
member nickname change is claimed here. Previous live tag checks confirmed both
roles; Discord prevents the bot from renaming the server-owner test account.

Character snapshots include private note history; retention/erasure and private
backup policy must be settled before wider multi-user use. Rebuild covers character
projections from snapshots, not reconstruction of membership, setup, safety or
outbox operational state; use full backup for those. Principal UUIDs supplement
existing snowflake membership keys; there is no retrofitted membership-to-principal
physical FK in this additive migration. Application transactions maintain registry
membership, and receipts explicitly reference principals.

The public repository contains bot source, migrations, synthetic tests and sanitized
evidence only. Private engine archives, official PDFs, canonical saves, local policy,
member/draft data, SQLite backups and credentials remain outside Git. No recovered
engine mutation or import, official mechanics, playable-sheet certification, v1.3.11,
AI, production security, multi-guild activation or external exactly-once delivery
is claimed. Stop before M2 pending owner acceptance and a separate work order.
