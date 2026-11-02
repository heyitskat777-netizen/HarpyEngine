# Security, Safety, Reliability and Operations

## Threat model

**Trust boundaries:** Discord messages, application-command options, user-provided files/attachments, AI output, event/scene links, model retrieval documents, admin actions, and external API responses are untrusted until validated. Discord username/display name and an in-character claim to be a GM cannot grant authority. Trusted identities are the authenticated Discord user and guild snowflake plus server-side membership and per-character permissions.

| Threat | Mitigation / acceptance test |
|---|---|
| Player acts as another Girl | Ownership checks at every command and component callback. No admin impersonation without explicit exceptional policy. |
| Campaign A reads Campaign B | Every query includes `campaign_id` and membership; cross-campaign test with duplicate callsign. |
| Secrets leak via `/sheet`/`/ledger` | Field-level projection whitelist, never `SELECT *` to response; snapshot and property tests. |
| Discord post prompts “ignore rules” | Treat as user/game content, no dynamic instruction elevation; model proposals checked server-side. |
| Handler learns GM-only fact | Different context builders and deterministic secret-canary tests. |
| Duplicate roll or effects | `(campaign_id,idempotency_key)` unique, `expected_revision` compare-and-swap, no extra RNG on retry. |
| Two PCs spend same shared resource | Transactional commit, revision fence; SQLite single writer in MVP. |
| Bot crashes after game commit before Discord post | Outbox retries, stable nonce/publication reconciliation; never reroll or recommit. |
| Bot crashes after Discord post before saving ID | May cause duplicate Discord projection; detect/reconcile using nonce; exactly-once delivery not guaranteed. |
| Invalid/expired component | Fetch current DB pending action; stale/expired returns safe refresh, no mutation. |
| Untrusted rules file overrides app | Imported ruleset is reviewed, checksummed and versioned; no untrusted Python execution. |
| Personally sensitive roleplay data retained | Consent notice, minimal retention, restricted access, export/delete plan, secure backups. |
| Public-adult-content or IP violation | Private prototype, review publisher licensing and Discord/OpenAI policies before any public launch. |

## OOC player safety

- `/safety pause` must work even during AI downtime and must not require Handler permission. It suspends implicated scenes and new narrative posts while preserving data for authorized review.
- Support scene lines/veils and opt-out boundaries, hidden from other players unless voluntarily shared. A fictional rule forcing a Girl to submit to Punishment does not permit coercion of the real player outside game agreement.
- No explicit sexual violence or nonconsensual sexual narration from AI. Mature themes can be represented non-graphically with player-established boundaries and group consent.
- Publishing a public bot is separate work requiring licensing and age/content review; private test does not confer distribution rights.

## Privacy and logging

- No default passive reading of all channels. Use explicit `/gm`, `/handler`, `/canon` and `/play` commands; later observational mode is opt-in by guild and by relevant participants.
- Store only necessary source excerpts for canon provenance. Don't mirror whole DMs or OOC chats into model memory. Provide retention and deletion rules before real players enroll.
- Log structured correlation IDs, event IDs, Discord response codes, latency and sanitized error type; do not log raw private dialogue, secrets or full model prompts.
- Database backups encrypted when real personal content exists; local `.env` excluded from Git; least-privilege bot permissions.

## Ops runbook requirements

1. `.env.example` with `DISCORD_BOT_TOKEN`, `DATABASE_URL`, optional `OPENAI_API_KEY` later, private guild IDs, logging levels. Do not ask users to paste tokens into a chat.
2. Migrations: `alembic upgrade head` as explicit process step; backup before changes; reversible migrations where feasible.
3. Startup: DB schema validation, register persistent views, resume pending actions and outbox; reconnect without rerolls.
4. Shutdown: flush in-progress transactions, persist jobs, do not lose Roll IDs or event acknowledgements.
5. Observability: `/health` and CLI status, jobs pending/failing, Discord rate-limit handling, backup age, event hash/rebuild verification.
6. Disaster recovery: documented restore-from-backup and event replay; synthetic restore test before real player pilot.
7. Deployment: one private guild first; avoid publicly reachable admin controls; use sandbox/DEV bot application separate from production later.

## CI test gates

- Compile/import, formatting/lint, fresh migrations, deterministic replay and snapshot rebuilding.
- Redaction tests: own-private versus other-public, secret field canary, AI Handler projection.
- Duplicate Discord callbacks and concurrent spend/change.
- Crash point test: between DB transaction, outbox enqueue, Discord send, ACK persistence.
- Property tests for Status exclusivity, roll idempotency, event sequence monotonicity, non-negative resources and correct campaign isolation.
- Human-reviewed narrative acceptance for AI modules, distinct from machine tests.
