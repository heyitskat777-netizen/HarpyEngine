# M1D — Raw dice, ledger and recovery

Authorized by the owner's continuation of M1. Complete the original M1 foundation
before starting M2. Preserve earlier server setup and owner-bound dropdown drafts.

## Work

1. Add migration for principal registry, versioned events, private draft snapshots,
   immutable raw receipts, safety pauses and transactional outbox. Preserve existing
   pilot data; back up before applying migration to the configured database.
2. Add campaign initialization/status, own raw OS-backed 2d6, receipt lookup, filtered
   event pagination, own pause/resume, and `/girl create` alias. Never imply official
   Play resolution or import recovered campaign data.
3. Persist inbox outcomes, expected revisions and distinct command event indexes.
   Test new-command concurrency and same-key replay before/after restart.
4. Deliver only explicitly published receipts to the saved ledger channel. Retry
   with durable leases, nonce and bounded reconciliation. Document possible duplicate
   external posts while proving canonical dice/events cannot duplicate.
5. Supply WAL-consistent backup/new-file restore, public-only export, snapshot rebuild
   and fresh offline synthetic seed. Never overwrite an active restore destination.
6. Run offline gates, record all evidence and limits, restart the authorized test bot,
   verify the guild command registry, and request human slash-command smoke.

## Acceptance

Map original M1-001 through M1-012 to executable tests with real temporary SQLite,
fake Discord and fixed test RNG. Include populated 0002 upgrade, two-campaign
isolation, private receipt denial, immutability, stale revision before RNG, both
commit/delivery crash points, replay/rebuild and WAL restore. Supplement with safety,
public export and SDK command tests. Preserve original case catalogue unchanged.

Record human dice/status/safety results separately from REST registration and offline
success. Full M1 acceptance remains pending until human smoke is supplied. Stop at
M1; no `/play`, AI or rules-certified builder work is authorized here.
