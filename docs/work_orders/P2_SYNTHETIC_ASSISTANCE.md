# P2 bounded deliverable — synthetic assistance and private review

Delivered at `28937b4`; focused CI43791181002 passed 101 tests including selected
existing dependencies. This completed work order remains the summary v1 scope.
The owner subsequently supplied the approved
[Director architecture](../AI_DIRECTOR_ARCHITECTURE.md). Its next
[P2-D1 work order](P2_DIRECTOR_OBSERVATION.md) adds synthetic scene observation
and batching later; it does not expand this summary's approval/application powers.

The current owner instruction authorizes this P2 backend increment and sanitized
source pushes before P1 human acceptance. It supersedes earlier roadmap timing
for this increment only. P1 remains RULES_SUBSET, with human acceptance and broader
coverage open. This work changes neither campaign approval nor the frozen live
v0.1.4 release.

## Fixed workflow

A currently authorized campaign member requests an audience-filtered context,
requests a summary against that context and current campaign revision, generates
a deterministic synthetic draft, privately approves or rejects it, and reopens the
recorded outcome after service restart. Approval records the reviewer's decision;
it grants no canonical or mechanical effect and queues no Discord publication.

The named completion demonstration is one persisted request → draft → approve →
reopen flow, plus rejection and a safe provider failure. Focused integrity checks
cover source privacy, owner/campaign binding, role revocation, stale revisions,
transaction rollback and same-key replay without duplicate records or effects.
Actual commands/results belong in the P2 acceptance report, not an inferred
full-regression or human-acceptance claim.

## Context and authority

Reuse authorized public character-sheet projections, then apply a fixed field
allowlist. Player context contains only the requester's permitted public metadata.
GM context may summarize permitted public roster metadata. Handler context is
narrower: public roster callsigns only. These are OOC references, not grants of
in-fiction observation. No owner notes, private setup choices, accepted-agreement
history, raw canonical state, campaign event dump or Discord transcript enters a
provider request. Absent observed knowledge remains absent.

The application server supplies a `GuildViewer` from verified Discord identity,
current guild membership and roles. The engine rechecks campaign membership and
binding on reads, writes and retries. GM audience requires configured administrator
access; Handler audience requires the current Handler appointment. An account with
both Handler and Pilot roles chooses an explicit audience for each request; those
contexts are never merged. Proposal review belongs only to its requesting owner,
without an administrator override.

## Implementation ownership and dependencies

- `src/girlframe/ai/`: strict versioned context/provider/proposal contracts, pure
  source-aware context filtering and deterministic synthetic summarizer. No SDK,
  credentials or network transport.
- `src/girlframe/services/ai_assistance.py`: trusted authorization, projection
  selection, revision-bound request/generate/review/reopen operations and existing
  command-inbox idempotency.
- Database metadata plus additive migration: immutable assistance revisions in
  the existing authoritative campaign store. No competing browser database and
  no automatic migration or mutation of the live database.
- Focused synthetic tests: bounded normal workflow and the affected integrity
  boundaries. Reuse pinned dependencies and existing store fixtures.
- [Activity integration handoff](../../integrations/ai_assistance/INTEGRATION_HANDOFF.md):
  versioned logical wire contract and ownership boundary. The Activity task owns
  its actual frontend/server adapter; its repository, backend and authentication
  handoff are still required before selecting or implementing HTTP integration.

## Explicit unsupported paths

Real providers/models, paid calls, provider credentials, external-data permission,
spending limits, freeform narration, source-aware fictional chronology, NPC control
and mechanical proposal application are outside this increment. Approval cannot
supply player dialogue/actions/consent, accept Bonds, activate a character, roll
dice, charge resources or bypass the existing source-backed game services.
Unsupported application stays visibly blocked.

No passive ingestion, bot restart, deployment, environment publication,
live-campaign changes or recovered-engine mutation is authorized here. Preserve
the optional second starting Bond, revision-bound setup-test exemption and distinct
Handler/Pilot roles. Existing native controls and durable workers remain the live
fallback. Integrating this source is not authority to replace them.
