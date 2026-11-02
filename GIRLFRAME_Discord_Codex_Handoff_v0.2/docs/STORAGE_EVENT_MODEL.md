# Persistent Database, Ledger and Event Contracts

## Design objective

**One append-only authoritative event history with separate materialized views** for sheets, dice, canon, knowledge and messages. No event accepted from raw Discord text without a valid action/ruling protocol. Do not confuse event-sourced facts with mutable operational data such as pending actions or delivery status; those operational tables are still governed by recorded state transitions and transactional writes.

## Minimum relational schema for M1 (SQLAlchemy + Alembic)

| Table | Key columns and rules | Notes |
|---|---|---|
| `guild_campaigns` | `id UUID PK`, `guild_snowflake TEXT`, `name`, `ruleset_id`, `revision BIGINT`, `created_at`, `status` | one active campaign/guild MVP; DB indexes ready for many |
| `principals` | `id UUID PK`, `discord_user_snowflake TEXT`, `created_at` | Display names are not authority |
| `campaign_members` | `(campaign_id,principal_id) UNIQUE`, `role`, `active` | FK campaign scopes every query |
| `characters` | `id UUID PK`, `campaign_id`, `owner_principal_id`, `callsign`, `girl_playbook_id`, `frame_playbook_id`, `status`, `revision`, `public_data_json`, `private_data_json` | M1 **draft only**, unimplemented published effects tagged as such |
| `events` | `id UUID PK`, `campaign_id`, `seq BIGINT`, `event_type`, `source_actor_id`, `scene_id NULL`, `source_message_id NULL`, `authority`, `payload_json`, `schema_version`, `ruleset_version`, `command_id`, `command_event_index`, `committed_utc`, `fictional_time NULL` | `UNIQUE(campaign_id,seq)` and `UNIQUE(campaign_id,command_id,command_event_index)`; many events can follow one command; inserts only |
| `rolls` | `id UUID PK`, `campaign_id`, `event_id UNIQUE`, `actor_character_id NULL`, `dice_faces_json`, `modifiers_json`, `roll_kind`, `ruleset_version`, `rolled_utc`, `command_id`, `roll_index` | `UNIQUE(campaign_id,command_id,roll_index)`; never change faces/spends after roll |
| `commands_inbox` | `(campaign_id,external_interaction_id) UNIQUE`, `actor_id`, `request_hash`, `outcome_json`, `status` | Duplicate same ID *and same payload* returns exact result; mismatch is error |
| `outbox` | `id UUID PK`, `campaign_id`, `event_id`, `channel_id`, `recipient_scope`, `content_ref`, `state`, `attempts`, `discord_message_id NULL`, `last_error` | delivery retries can duplicate Discord sends; reconciliation required |
| `schema_meta` | current migration version | Alembic owns physical schema |

**M2–M4 additional tables:** `frames`, `assets`, `identities`, `tags`, `bonds`, `permissions`, `ruleset_versions`, `actions`, `choice_requests`, `scenes`, `scene_participants`, `scene_dependencies`, `world_facts`, `knowledge_grants`, `missions`, `mission_members`, `obligations`, `ai_proposals`, `audit_corrections`, `safety_pauses`, `backups`. Typed effects can be stored as event payloads and projected onto these tables. Add tables by migrations, not direct SQL edits.

**Production hardening:** no physical event deletion on ordinary editing; do not include raw secrets in generic event-list queries. `private_data_json` is an implementation placeholder, not an excuse to return the whole object to all callers. Secrets need per-field visibility and authorization when M3/M4 ships.

## Event transaction boundary

1. Adapter receives interaction, authenticates external Discord principal and validates guild/channel context.
2. Service checks `commands_inbox` for the interaction ID and matching payload hash. On exact repeat, return stored result (never regenerate dice).
3. Begin DB transaction. Scope by `campaign_id` and principal. Verify expected revision, owner authority, pending action state and ruleset version.
4. Create a pending action or legal Play declaration. If rolling, sample **once**, record immutable faces, validated modifiers and resource spending atomically. If choices are pending, **do not** apply post-roll effects yet.
5. Emit authoritative event(s) and update projections, increment versions; enqueue public/private Discord projections.
6. Commit; return a durable receipt with `event_id`, `roll_id`, `state_version`, `pending_choice_ids`, `output_visibility`.
7. Worker sends projections; on failure, retry delivery without new game events or dice. Save message ID when known.

**Heat timing**: pre-roll spend and any identity-marking that grants Heat must be validated and committed *before* dice are sampled; post-roll Tags can affect outcome only when printed rules permit. A database transaction can enforce exact ordering with distinct domain events inside one action lifecycle.

## Canon event lifecycle

- `DECLARED`: player's intended action; no world outcome.
- `WAITING_FOR_RULING`: GM/facilitator must determine applicability/fictional trigger.
- `PRE_ROLL_LOCKED`: legal Heat/resources and available options committed.
- `ROLLED`: immutable genuine dice recorded.
- `WAITING_FOR_CHOICE`: other human/Handler/GM required decisions.
- `RESOLVED`: every mandatory consequence exists, options complete and consistent.
- `COMMITTED`: canonical state effect applied and event history appended.
- `PUBLISHED`: appropriate Discord projections attempted/confirmed. This is a **delivery** status, not mechanical state.
- `BLOCKED`: missing rule, stale revision, safety pause, target unavailable or adjudication needed. Never silently turn blocked into success.

A non-rolled narrative event can skip pre-roll and roll, but cannot bypass validation/authorization.

## Knowledge and confidentiality model

- `world_fact`: what is actually true (GM view, source and confidence).
- `character_knowledge`: (fact ID, knower ID, witnessed event ID, acquired fictional time, what part they know). Some facts may have false reports; a character believing a lie does NOT rewrite objective truth.
- `artifact_visibility`: which *real Discord accounts* may see the stored text/evidence. This is **not** the same as what a fictional character knows.
- `private_scene`: membership, location, and real/private access policies. Discord admin permissions may supersede thread privacy, so truly sensitive OOC notes should remain in private backend views, not simply a private Discord thread.

## Corrections and retention

Append `event.corrected` containing the prior event ID, reason, affected projections, and reviewer. A correction to a prior Play must flag causal descendants for review before treating future state as valid. Avoid hard-deleting shared fiction. Distinguish retention and erasure of **real personal data** from preserving in-game mechanical audit. Provide deletion/export workflows and privacy notices before multi-user live release.

## Worked example: synthetic Oldgen Status event

- The **human-controlled Oldgen** selects *Old Dog, New Pups* and plays out the advice; the exact printed rules govern tier and recipient.
- The engine commits one roll with faces and modifier receipt.
- On a valid published 8–10 outcome, it emits `StatusExchangeApplied` for Oldgen↔Ace plus `OneUseMaximAdded` (and later `OneUseMaximConsumed`).
- Two character sheet projections update. The receiving Girl's emotions and voluntary choices remain with her human player.
- The ledger is queryable as the original Play → roll → options → Status effects → knowledge/scene consequences. Test cannot assume a particular Girl named MAUL or AYLA belongs to the new campaign.

## Versioning / rebuild guarantees

- Every committed event has `schema_version`, `ruleset_version`, `command_id` and `command_event_index`. A single `/play` can legitimately produce several related events under the **same** command but with different indexes; deduplication must not accidentally block those events.
- Every reducer has deterministic replay semantics; rebuild from events+versioned snapshots reproduces roll history and visible projections byte-equivalently aside from generated display timestamps.
- SQLite snapshot and WAL backup policy is documented and tested. Verify restore integrity, migration status and event signatures/checksums if introduced.
