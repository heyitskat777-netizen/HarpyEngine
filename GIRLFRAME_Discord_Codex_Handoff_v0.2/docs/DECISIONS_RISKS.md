# Decision Register and Risk Assessment | v0.2

## Proposed ADRs

| ADR | Proposed decision | State / tradeoff |
|---|---|---|
| 001 | Single authoritative event journal + derived sheets/roll/canon views | Proposed, modest complexity for auditability |
| 002 | Python 3.12+, `discord.py`, SQLAlchemy, Alembic, SQLite WAL | Proposed, small private pilot; PostgreSQL later |
| 003 | Engine / Coordinator / GM / Handler / Discord adapter separated | Fixed boundary, modules may share process |
| 004 | AI-free M0/M1 | Fixed milestone policy, tests before narrative |
| 005 | Only real player controls voluntary Girl actions | Nonnegotiable |
| 006 | Separate GM/Handler context builder with server-side filtering | Nonnegotiable |
| 007 | Slash/interactions first; passive channel reading later opt-in | Proposed |
| 008 | Two time axes and scene dependencies | Fixed |
| 009 | Corrections append superseding events | Fixed |
| 010 | Official rules > approved house rules > experimental skill code | Fixed |
| 011 | No advance from real-world inactivity | Proposed default |
| 012 | Private pilot pending licensing/mature-content plan | Fixed release gate |
| 013 | Human facilitator for ambiguous ruling and player safety | Proposed |
| 014 | One active campaign per guild initially; multi-campaign DB-ready | Proposed |
| 015 | Post-roll choice workflow; immutable dice | Fixed |
| 016 | AI emits structured proposals only, no direct mutations | Fixed |
| 017 | DB game commit exactly-once via idempotency; Discord send at-least-once | Fixed engineering reality |
| 018 | `/play` wizard prioritized in M2 before AI | Proposed UX priority |
| 019 | Off-Duty/Strain recursion must fully complete before closed | Fixed fidelity gate |
| 020 | Explicit consent and private scope for RP transcript ingestion | Fixed privacy boundary |

## Decisions owner can defer until later

**Before M1:** repository host and privacy; preferred Python tooling/hosting; who is campaign owner/facilitator in your private group; whether initial bot uses single guild; backup location and data retention for test accounts.

**Before M2:** exact official rulebook/errata version; initial 3–5 Plays implemented; private vs public roll visibility; character creation extent; permitted house rules and optional Personal Stakes.

**Before M4:** whether auto-summary of ordinary RP channels is enabled; consent policy; Discord threads versus separate private channels; handling abandoned scenes and dual-location paradoxes; who may approve corrective canon events.

**Before M5/M6:** model/provider and spend budget; Handler personality configuration; whether AI can trigger events when players are not posting (default only when fictional trigger explicitly due); human review threshold; privacy notice about AI processing.

**Before public release:** creator/IP license, age/safety restrictions, privacy/deletion, Discord permissions/intents, model safety compliance, scaling, support/moderation responsibilities.

## Top risks ranked

| ID | Severity | Risk | Mitigation/gate |
|---|---|---|---|
| R-01 | Critical | AI forges player decision | Authenticated choice only; role-scoped contract tests |
| R-02 | Critical | Narrative contradicts committed state | Fact-grounded proposal/revision checks, rejection path |
| R-03 | Critical | Published Play incompletely implemented | Full rules registry, exact options and independent certification |
| R-04 | Critical | Secrets leak across characters/campaigns | Backend field filters, canary tests, owner scoping |
| R-05 | Critical | Discord retries generate duplicate dice/effects | Transactional inbox unique key + idempotent receipts |
| R-06 | High | SQLite and Discord send disagree | Outbox and reconciliation; warn that delivery is at-least-once |
| R-07 | High | Out-of-order play-by-post chronology | Timestamped scenes and causal barriers |
| R-08 | High | Handler mistaken for GM omniscience | Separate context, reviewed knowledge grants |
| R-09 | High | Unknown rules softened as fiction | Unsupported-rule block; facilitator escalation |
| R-10 | High | Public distribution of copyrighted/mature material | Private-only pilot pending rights and platform review |

## Triggers to halt rollout

- A human Girl's speech/consent or legal choice can be fabricated by AI.
- A signed mission/roll/canon event changes from a Discord message edit or retry.
- A secret appears in a Handler context without documented knowledge gain.
- A recursive Strain/mandatory Play is silently waived.
- The system declares a Harpy in custody after her established escape with no new event.
- A test uses real The Long Winter T194 campaign state or private player data as a generic fixture.
- API secrets or official PDFs appear in a public Git repository.
