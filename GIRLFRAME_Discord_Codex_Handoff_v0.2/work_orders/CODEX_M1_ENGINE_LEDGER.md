# CODEX WORK ORDER M1 | Persistent Campaign, Character, Dice and Canon Ledgers

**Task:** Build a **runnable AI-free Discord bot**. Read M0 acceptance report and `planning/docs/STORAGE_EVENT_MODEL.md`, `planning/docs/DISCORD_UX.md`, `planning/contracts/*`, `planning/verification/REGRESSION_CASES.json`, plus `planning/AGENTS.md`. If M0 is blocked, STOP.

## Required systems

1. **DB:** Alembic migration for campaign/guild, principals, membership, synthetic GirlDraft, event journal, roll receipts, idempotent command inbox and transactional outbox. SQLite WAL, FK constraints, unique campaign sequence, inbox interaction keys, and event `(command_id, command_event_index)` pairs. One command may emit multiple distinct events.
2. **Typed services:** `create_campaign`, `join_campaign`, `create_girl_draft`, `get_public_sheet`, `get_private_sheet`, `get_status`, `roll_basic`, `get_roll_receipt`, `list_events`, `rebuild_projections`, `enqueue_projection`, `mark_delivery`. Require authenticated principal and campaign scope, idempotency key, expected revision for mutations.
3. **Discord:** `/campaign create/join/status`, `/girl create`, `/sheet`, `/roll basic`, `/roll show`, `/ledger`, `/health`. `sheet` of another player's Girl shows public info only. Default setup view ephemeral.
4. **Dice:** OS-backed real two-d6 roll on a basic test command. Stable receipt with faces, total, actor ID, campaign, timestamp; no automatic GIRL FRAME Play claims in M1. Inject fixed RNG for unit tests only.
5. **Persistence:** restart/reconnect restores all views and committed events. At-least-once outbox delivery with nonce and reconciliation. CLI migrations, synthetic seed, snapshot/export, backup and restore.
6. **Docs:** setup instructions, Discord Developer Portal bot application setup and intent permissions, test transcript, open known limitations.

## M1 critical invariants

- A Discord player cannot write a Girl owned by someone else. Owner/facilitator roles are not implicit power to author another PC's voluntary action.
- Two guild campaigns cannot leak data even with same callsign or Discord user ID; all resource keys scoped by campaign.
- Duplicate interaction ID with identical payload returns **same roll**; same ID with different payload is a typed conflict. On restart, still no new roll.
- Concurrent revision conflict commits at most one command; the loser gets `STALE_REVISION` and no spent Heat or dice.
- A Discord message edit or deletion does not edit the event journal.
- Private fields are filtered **server-side**; a player receiving a public projection cannot ask for full object serialization.
- No RNG calls on recovery/retry of a recorded dice result.

## Tests (mandatory)

Implement at least `M1-001` through `M1-012` in `planning/verification/REGRESSION_CASES.json`, using fake Discord interaction adapter and real temporary SQLite DB. Verify duplicates and crash points. Include a two-campaign information-isolation test and a post-restart replay test. Test the outbox sends may duplicate but **game state never does**; do not claim external exactly-once delivery.

## Manual Discord smoke (private guild only, after tests)

```
/campaign create name:Synthetic Pilot
/campaign join
/girl create callsign:SYNTH_A girl_playbook:oldgen
/sheet
/roll basic
/roll show <receipt>
/ledger
```

Use synthetic identities and no real The Long Winter data. Send stable receipt IDs in visible output. Include screenshots or redacted transcripts if safe.

## Acceptance

Migration fresh DB, full test suite, lint, fake and real Discord smoke (real if credentials configured by project owner), restore, access controls, event replay, README and `reports/M1_ACCEPTANCE.md` with actual evidence. If Discord credentials are unavailable, list real-guild smoke as **SKIPPED**, not passed. Do not assume code is production-ready.

**STOP after M1.** M2 `/play` is not included unless independently authorized.
