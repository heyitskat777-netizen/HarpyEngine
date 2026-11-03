# M1 ledger implementation decisions

M1 owns a new SQLite pilot, not the recovered engine's campaign. Only raw dice
receipts and draft metadata are implemented. There are no official Plays, modifiers,
Heat, canon effects, AI proposals or legacy finalizer calls.

## Command transaction

`CampaignLedger` reuses `OnboardingStore`'s campaign/guild binding, explicit database
membership and `BEGIN IMMEDIATE` serialization. It validates membership again for
receipt replay, so an inactive account cannot replay a formerly accepted command.
The inbox hashes actor, operation and semantic payload. A saved command returns
its original outcome before stale-version or safety checks and never calls RNG.
Changing publication intent under the same key raises `IDEMPOTENCY_CONFLICT`.
For ledger operations, expected revision is checked on first execution only and is
excluded from that semantic hash. Draft saves retain their existing owner-revision
hash and stale-form behavior.

New rolls validate current campaign revision, safety state, saved own draft and,
for public delivery, the managed ledger mapping. Only then does `OsDice` sample two
`secrets.randbelow(6)+1` faces. Tests inject `FixedDice`; the runtime has no RNG setting.
One transaction inserts `dice.rolled` index 0, the immutable receipt, `dice.recorded`
index 1, inbox outcome and optional outbox. Campaign sequence increases per event.
This clarifies the historical M1-007 phrase “one event”: exactly one **rolled** event
exists, plus the separately indexed recorded event required by multi-event commands.

`RollReceipt` is a strict immutable Pydantic model with exactly two integer faces,
range checks and sum validation. Its internal envelope records owner, callsign at
roll time, scope, timestamp, source, stable IDs and revision. `contract()` projects
an already-authorized receipt to the illustrative handoff roll schema (kind `2d6`,
zero modifiers, no Play, state `rolled`). Discord never dumps this full envelope;
it renders callsign, faces, total, receipt ID and timestamp explicitly.

## Visibility and authority

Reads check configured guild and active campaign membership. Private rolls are
visible only to their actor; public rolls to joined members. Administrator status
does not override private receipt or sheet ownership. Ledger pages filter in SQL
before selecting an explicit field allowlist. Generic payloads, snapshots, private
notes, actor IDs and inbox contents are never returned by event pagination.

The old `/campaign_status` audience rule remains in addition to database status
checks. Both status slash forms show M1 state, not a second legacy-engine status.
The local `engine-status` CLI remains the explicit read-only reference.

OOC pauses are one row per participant. Pause requires membership but deliberately
accepts an old expected revision: safety must win over ordinary metadata races.
Resume checks revision and can remove only the caller's row. All requests must be
cleared before new rolls resume. Neither reason nor fictional punishment is stored.

## Schema and snapshots

Migration 0003 is additive on populated 0002 databases. It registers principals
with stable UUIDs while keeping snowflakes as membership natural keys. Existing
membership is backfilled; application membership checks and service transactions
maintain the registry. Existing membership does not acquire a new physical principal
FK in this migration; receipts reference principals explicitly. All queries include
campaign scope, and binding conflicts are refused even on reads.

Events have sequence and `(campaign, command, index)` uniqueness, schema/ruleset
versions, and private default visibility. Actor IDs and kinds record provenance;
local repair uses `system:local_operator`, never a forged Discord user. Operational
metadata remains private unless deliberately projected as a public dice receipt.

SQLite triggers reject UPDATE/DELETE of events, rolls and character snapshots.
Every new saved draft gets a private versioned snapshot in the same transaction as
its audit event. Migration captures each older draft's current revision with a null
source event to identify the migration baseline. Old overwritten revisions cannot
be recreated. Rebuild selects the latest snapshots and restores character views;
missing snapshot coverage stops repair rather than deleting unmatched rows.
Membership, setup, safety, role mappings and delivery are operational records whose
full recovery uses backup, not a claimed universal event reducer. Recorded rolls
are already authoritative immutable records and are never regenerated.

## Delivery and maintenance

Only `publish:true` enqueues a public roll. Outbox references the exact managed
ledger ID, receipt/event and stable nonce. A worker claims with a 120-second lease
and random claim token, outside any HTTP transaction, with bounded retry backoff.
Only the matching claim can record the message ID. Reconnect does not create extra
workers; expired leases resume after restart. Sending and acknowledging remain
separate operations, so external exactly-once delivery is not promised.

On retry, the gateway can reconcile the latest 50 messages of that ledger by bot
author plus receipt marker when Read Message History is available. Otherwise a
retry may post another copy with the same receipt/nonce. The SDK does not expose
Discord's `enforce_nonce` flag; nonce alone is not a deduplication guarantee. No
passive roleplay ingestion or public delivery of private receipts is enabled.

Local backup uses SQLite backup API and verifies integrity and foreign keys; restore
refuses existing destinations. Copying just the main DB file while WAL is active is
not the backup procedure. Local exports allowlist public fields, and snapshots/backups
remain private. Restore preserves pending deliveries, which may retry if used as a
live DB. Stop the bot before switching databases and keep the original available.

This is pilot infrastructure, not certified rules or production security. Before
multi-user launch, define retention/erasure of immutable private snapshots and
backups, host supervision, and broader operational access controls.
