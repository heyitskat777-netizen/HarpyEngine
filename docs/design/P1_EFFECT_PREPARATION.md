# External-effect preparation slice (unused)

November 10, 2026. This implements only durable preparation from the proposed
P1_EXTERNAL_EFFECT_JOURNAL.md contract. It is not the full external-effect journal,
an actor freeze, an external-I/O gate, a legacy quarantine, or safe shelving.

Migration 0017 freezes its original four-table definitions locally. Additive 0018
installs append-only guards for preparations, actor incidence, physical channels,
resource links and referenced source events. Update, delete and replacement are
rejected, including explicit occupied SQLite rowids with recursive triggers off.
Actor/token mapping uses parsed identity rather than JSON whitespace. Downgrade
refuses retained evidence. Existing rows are not rewritten or certified.

prepare requires an already-open SQLite transaction and never commits it. The
referenced campaign event must carry the exact canonical preparation in its
external_effect_preparations list. Replay compares the full body, every redundant
effect field, original actor projections, resource binding and destination registry.
Conflicting legacy evidence fails replay; this is not a legacy quarantine sweep.

Event-payload matching is evidence binding, NOT authenticated provenance. Any
writer able to mutate an unreferenced historical event can put matching evidence
there. Transaction origin, source authorization, complete incidence, actual actor
and source generations, and destination authority remain unverified. The service
derives canonical actor UUID tokens; SQL guards preserve semantic uniqueness and
existing token/identity mappings, not the cryptographic derivation of the first
inserted token. Production callers do not yet exist. No row is safe to dispatch.

reserve always fails closed. The SQL state constraint admits only prepared records.
No attempts, leases, handles, dispatch tokens, acknowledgments, reconciliation,
permission ownership transfer, snapshot capture or network I/O are implemented.
In particular there is no outcome reset/retry API and no code path that treats a
lost response as not dispatched. Existing workers are NOT protected by this slice.
Adding preparation tables alone neither fences old binaries nor makes restore safe.

Next integration requires canonical source/actor admission, complete incidence,
shared channel ownership, attempts with durable intent, one-shot handles, exact
result evidence and atomic source projection, typed reconciliation, legacy quarantine
and all three gateway/worker paths together. Unknown outcomes must remain blocking.
Only after those and the separate canonical shelving guard exist can drain and
activation be implemented. No broad synthetic guard replaces those requirements.

Tests authored cover exact event binding, rollback and replay, physical-resource
conflicts, immutable update/delete/declared-key replacement, occupied-rowid
replacement with recursive triggers off, JSON-whitespace actor duplication, legacy
redundant metadata rejection, migration preservation and downgrade refusal. Root
reported six initial tests passed (0.62s), then nine revised tests passed (0.67s).
The latest command/index multirow replacement regression covers both runtime and
migration-created schemas; root reports both passed (0.48s) after the final correction.
A separate database migration node passed (0.54s) before that final correction.
These are segmented results, not one full-suite run on the final snapshot. Targeted
Ruff passes. Independent static re-review found no further concrete blocker within
preparation-only scope; it ran no tests. Final-candidate regression, broader
migration/privacy/restore and human acceptance remain pending. Bot remains off; no live migration or publication.
