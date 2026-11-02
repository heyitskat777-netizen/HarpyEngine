# Architecture and Module Boundaries

## Logical diagram

```text
Discord commands/components/threads/messages
                 |
             Adapter (authn + ack/defer + typed request)
                 |
        Service / Scene Coordinator (authz + workflows)
          /      |           |              \
   Engine       GM AI      Handler AI       Outbox Worker
    |             |           |                |
 Pure rules   World-only   Handler-view     Discord API
    \             |           |               /
       Proposal validator and event transaction
                     |
         Event store + projections (database)
         + knowledge/witness + pending actions
```

A *logical* separation is sufficient: GM and Handler may use one model provider and common transport, but must use separate request context builders and structured response types. Neither can send arbitrary SQL or substitute a player's decision.

## Core domain components

- `engine/rules_registry.py`: versioned identifiers, published page and printed options verified against the supplied rulebook, legal preconditions, effect reducer. No Discord or OpenAI imports.
- `engine/rolls.py`: OS RNG provider in production, injectable deterministic RNG in tests; records immutable faces/modifiers/spend, enforces Heat timing and Tag limits.
- `engine/effects.py`: pure reducer of committed events into campaign/character/world state; no ad-hoc setters from AI.
- `engine/permissions.py`: separate player authority, status hierarchy, real OOC role and fictional command authority. OOC moderator privilege does not grant the right to impersonate a Girl.
- `service/commands.py`: accepts authenticated typed commands and revision, creates action rows, emits events, applies reducer and outbox within transaction.
- `scenes/coordinator.py`: scene participants, presence, fictional timestamps, pending choices and review queue, lock barriers and response routing.
- `gm/world.py`: plans NPC/Gorgon/Harpy/mission and setting proposals from GM-visible, campaign-scoped facts; never direct mutation.
- `handler/agent.py`: acts as a named Handler with her own mechanical sheet, distinct knowledge, agenda and current obligations; orders are in-world facts only once witnessed and committed.
- `ai/context_builder.py`: independent whitelists per audience; no raw state dump passed to Handler. GM may read relevant GM secrets, but still cannot choose for PCs.
- `ai/proposal_validator.py`: strict JSON schema and references to existing entity IDs, state version and permissions. If result is uncertain or contradicts canon, reject/ask facilitator rather than improvising.
- `discord/commands.py`: interactions, static UI/projection, deferral, authorization and option rendering only. No model prompt assembled here.
- `discord/views.py`: Play wizard, pending player choice, sheet, mission board; stable custom IDs and state reloading, not in-memory-only transient truth.
- `delivery/outbox.py`: delivery job queue with Discord acknowledgement IDs, retries, reconciliation, allowed mentions and privacy scopes.
- `database/*`: campaign-scoped repositories, SQLAlchemy 2 models, Alembic migration and backup/export path.

## Five authority invariants

**I. A player may declare but not finalize contested fiction.** A user message like “I destroy the station” is a declaration, not a canonical station destruction.

**II. AI proposals are not mutations.** The GM may propose an attack, the Handler may propose a Punishment, but each must be authorized by a typed rule/path. Unknown published rules are blocked.

**III. No player proxy.** An unresponsive PC blocks only scenes or actions requiring that PC's choice. The bot may describe involuntary, published consequences without manufacturing feelings, agreement, consent, choices or voluntary words.

**IV. Knowledge must be provenance-bearing.** `world_fact` and `knowledge_gain` are different entities; a GM-only fact is not automatically known to Handler; knowledge must have an observed source and witness.

**V. Canon is not chronology by Discord message order.** Store UTC message/commit timestamps, an independent in-fiction scene clock, and causal dependencies. A scene can be paused without advancing global time.

## Exact-once versus at-least-once

- **Database mutation:** at most one **result per command idempotency key**; a command may produce multiple uniquely indexed events. One roll per `(command_id, roll_index)`, guarded by unique indexes and transactions.
- **Discord delivery:** API sending is not atomic with SQL commit. If the API succeeds but the process crashes before saving the message ID, the next retry may duplicate the Discord post. Use a delivery nonce printed on the message, bounded retries, lookup/reconciliation when possible, and compensating projection supersession; do **not** promise exactly-once external delivery.
- **AI invocations:** may be retried, proposals have `proposal_id` and `based_on_state_revision`, stale proposals cannot commit, and rerun model output can never reroll previously committed dice.

## Deployment topology, initially

One Discord Gateway bot process plus one logical job worker and one SQLite database in WAL mode on a persistently mounted disk with ONE database writer. This can be one Python process with independent tasks in M1; do not imply distributed locks or multiple writing workers on SQLite. Provide CLI migrations, backup/restore, health and diagnostics. PostgreSQL becomes necessary before independently scaled multi-process workers or multi-host deployment.

## State presentation contract

Events/projected sheets have `state_version`. Discord component inputs include a stable action/session id and expected version. Clicking a stale button returns an updated view or `STALE_REVISION` without mutating state. Discord messages are editable projections and may disappear; reconstruct from the database on restart.
