# P2-D1 — synthetic Activity scene observation and durable batching

Status: implemented synthetic D1 slice; focused evidence is recorded in
[the D1 report](../../reports/P2_DIRECTOR_OBSERVATION.md).
Parent: [approved Director architecture](../AI_DIRECTOR_ARCHITECTURE.md).
This is P2 synthetic engine-side preparation under existing owner authorization.
It enables no real transcript collection, provider call, live mode or deployment.

## Frozen implementation decisions

- Native `keep_your_head` with its actual `m2.choice_resolved` event, canonical
  history entry and matching receipt is the first supported Play source. All child
  families and private/delegated/specialized variants are blocked. Any unresolved
  scene-required work blocks this conservative first adapter.
- Default service is Off. A trusted local synthetic harness explicitly constructs
  `DirectorObservationService(store, synthetic=True)`, configures off/shadow policy
  and records each participant's own revision-bound consent. This flag is never
  accepted from a browser or used to enable actual transcript collection.
- Input is participant-visible IC text, at most 1,000 characters, with an explicit
  Pilot/Handler speaker validated against actual identity/controller/casting. OOC
  submissions are ignored without storing their text or resetting timers. There
  is no AI/system-origin ingest endpoint. IC submission respects scene chat locks.
- Same-key retries return metadata only and recheck current authorization. Own
  IC edits append source revisions; audience changes require privacy review.
- Three tables in additive migration `0022`: immutable source revisions, mutable
  scene policy/consent/frontier and durable token-bound run claims. Frozen claims
  contain up to 20 current source revisions and three recent-tail references.
- Claim leases last 120 seconds. Server metadata retains scene/policy/consent/
  canonical revisions, original bind event and a guard over input, membership,
  safety history, policy, scene actions/choices/locks and required work. A failed
  synthetic acknowledgement consumes nothing; replay is stable. No model runs.
- Unread history with a different audience is blocked, not silently discarded or
  widened. Real retention/redaction and dynamic audience reconciliation remain
  outside D1. Workers invoke the source adapter explicitly; no worker is started.

The sections below retain the agreed workflow and acceptance scope. Planned
operations are now implemented with signatures in the Activity handoff and code.

## Fixed normal workflow and effects

An already joined synthetic participant submits IC messages to an already bound,
opted-in synthetic scene through a trusted service adapter. The service persists
source identity/revision and input generation. A fake-clock scheduler produces one
scoped, leased review batch after quiet/size/age eligibility. A trusted synthetic
review completion acknowledges only its frozen frontier. A fresh service reopens
the same status; duplicate input/triggers/claims do not duplicate work.

One actual supported completed Play supplies its real same-campaign action,
receipt and committed result as a second eligible trigger. A pending human choice
or unresolved mandatory child does not count as that completed Play. Reuse an
existing likely-flow Play fixture; freeze the exact supported completion adapter
and fixture before coding. Other source families remain explicitly unsupported.

Effects: observation/frontier/lease and trigger metadata in the one existing
campaign store; private operational audit with no message bodies. No mechanical
state changes, fictional time progression, model inference, narration, publication,
costs, resource changes, new dice or player choices. Synthetic review completion
proves cursor handling only; it is not an implemented AI `WAIT` decision.

## Ownership, files and reuse

Root coordinates this one workflow. If implementation is delegated under the
current staffing policy, assign a single bounded file owner; do not overlap edits.
Proposed new paths, subject only to a demonstrated naming/dependency conflict:

- `src/girlframe/ai/observation.py`: strict source/batch/status contracts and pure
  quiet/size/age eligibility with injected time. No model transport or storage.
- `src/girlframe/services/director_observation.py`: trusted Activity source append,
  completed-Play source verification, claim/freeze, acknowledgement and status.
- `src/girlframe/database/director_schema.py` and the next unused Alembic revision:
  minimum observation/scene frontier/trigger/lease records; no real-data backfill.
- `src/girlframe/database/tables.py`: register that metadata only.
- `tests/test_director_observation.py`: focused normal flow and affected integrity
  checks; reuse migration and existing Play setup/choice helpers.
- Existing acceptance report/CI selection: update once at the coherent handoff.

Reuse `OnboardingStore._write`/`transaction`/membership/binding, existing pause and
current authorization checks, `GameService.scene`/`action`/`pending`/owned choices,
immutable `m3_scene_contexts` and source-required-work records. Do not copy whole
GameState into context or invent a parallel campaign/scene store. Persistent
observations reference the actual scene ID and bind event; a channel rebind must
not relabel earlier input. Keep existing summary v1 models and service unchanged.

The current channel-bound service is a known dependency: resolve stable scene ID
to its verified binding server-side; an Activity instance is not a scene. The
frontend/backend framework and authentication remain pending from the Activity
task. Test a transport-neutral verified-viewer adapter; implement no HTTP framework.

## Logical service contract to implement

Names below are planned service operations, not existing methods or HTTP routes.
All wire IDs are strings. Server-owned identities/revisions are never model output.

| Operation | Inputs and enforced boundary | Result |
|---|---|---|
| `append_scene_input` | Verified viewer, stable command key, expected scene revision, scene ID, bounded text and IC/OOC intent; verify membership, actor binding, current subscription/consent and allowed visibility | Server-held source ID/revision/order plus current generation; exact replay returns original result |
| `observe_committed_play` | Trusted internal source reference; verify original scene/action/receipt/outcome and resolved mandatory work | One deduplicated trigger or safe unsupported/pending result; never accepts browser completion claims |
| `claim_review` | Trusted worker, injected clock, current policy; atomically verify eligible unread work and acquire a claim | Bounded frozen frontier, revisions, triggers and worker lease token; one concurrent decision per scene |
| `acknowledge_review` | Trusted synthetic review result plus current claim token/frozen generation | Advance only the successful reviewed frontier; reject stale claims; preserve newer unread input |
| `status` | Verified viewer and scene ID; recheck current audience | Permitted mode/eligibility/next review/pending status, without private context or other owners' messages |

Freeze exact typed signatures and maximum input/context sizes before coding.
Scene observation permission and fictional character knowledge remain distinct.
Persist retention-policy references/redaction markers without claiming real-data
retention policy is settled. Bound message/tail payloads explicitly and reject or
split excess input; no silent loss while advancing the cursor.

Synthetic fixtures may configure observation/shadow eligibility; runtime mode
defaults Off. Off makes no Director inference/optional publication. D1 performs
no inference in any mode and implements no path to live actions. Do not create
configuration UI/admin endpoints or install synthetic approvals in a real policy.

## Scheduling and recovery requirements

- New accepted eligible player input moves quiet deadline by 120 seconds;
  duplicates, OOC/AI output and typing/presence do not. Material source edits
  invalidate old batches; distinct-message counts do not count revisions twice.
- Twenty unreviewed messages or oldest age 10 minutes may produce an
  observation-only review during active conversation. Honor the 120-second minimum
  routine review interval. Explicit/required engine triggers are separately typed.
- A plain tick on an unchanged scene does not claim more work. A synthetic
  completed review consumes only its frozen input/triggers; failures consume none.
- Persist pending/expired leases and unread input across restart. Membership,
  scene closure/rebind, safety, policy/consent/visibility or relevant input changes
  invalidate affected claims. An acknowledgement cannot delete newer input.
- Never hold a database writer transaction across external work. D1 has no model
  call; its claim/ack boundary prepares future out-of-transaction evaluation.
- Keep human pending choices and locks authoritative; unrelated allowed scenes
  continue. Source ingestion never satisfies required work or unlocks a Play.

## Completion demonstration and focused checks

Use a deterministic fake clock and synthetic messages only. Demonstrate one
scene submission → quiet eligibility → frozen claim → successful acknowledgement
→ fresh-service status, plus the actual supported Play-trigger route. Reuse a
compact fixture for relevant privacy/staleness/retry checks, without speculative
role/tier matrices or a new simulation framework.

Required checks for this work unit: duplicate input does not reset quiet time;
20-message/10-minute active conversation yields only review eligibility; foreign
scene/owner and missing consent reject; OOC/AI echoes do not feed a loop; pending
Play choices/children stay pending; completed source triggers once; stale claim or
provider-equivalent failure consumes no unread input; rollback/restart and exact
replay preserve records. Include fresh/populated migration preservation checks
because new persistence is affected. No real provider or publication test is needed.

This covers the foundation portions of DIR-01–05, DIR-07–09 and DIR-11–12; it does
not close the full Director matrix. Run focused pytest and lint/format over all
changed Python (including shared modules/migration/tests), applicable source types,
planning/registry/repository checks and `git diff --check`. Record exact source,
commands, pass/fail results and remaining gaps. Retain the existing full-candidate
regression and human review gates; do not rerun full gameplay merely for D1.

## Unsupported and next boundary

No real Activity login/HTTP/realtime integration, actual player transcript capture,
external provider, five-way model decision, autonomous speech/world event, generic
mechanical application, new scene creation/chronology engine, retention/deletion
rollout or worker startup/deployment belongs to D1. Broader Play families need
their own source completion adapter. Actual knowledge/disclosure and fictional
chronology records require a subsequent bounded context workflow.

After D1 evidence is recorded, freeze the next knowledge/chronology and synthetic
shadow-decision workflow using the canonical architecture. Do not silently turn
the existing approved-summary record into canon or widen its application scope.
