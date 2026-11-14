# Actor-specific shelving boundary: implementation decision

Status: design only, activation remains unavailable. This report is against v22
intake, reconstructed from the required-Mock checkout plus shelving-intake.patch.
No transaction guard prototype or v23 lock prerequisite was imported. No runtime
code changed, no pytest run, no live connection, publication or deployment.

## Decision

A safe actor freeze cannot be added as a bounded guard around the current event
method. Do not activate shelving using a partial implementation. The smallest
credible implementation is a supported-command boundary with typed effect
classification, actor-indexed operational dependencies, and a worker drain
protocol. Unknown gameplay operations must reject while any shelf is active;
known independent operations may proceed. This is not a campaign-wide snapshot
freeze: refusal depends on an operation's proved effects, not merely on another
player being absent. Initially the supported set will be deliberately small.

## Concrete evidence in this baseline

- `services/onboarding.py::transaction` uses BEGIN IMMEDIATE and commits after its
  caller returns. This is the existing SQL atomicity boundary. `_write` validates
  its authorize callback before cached replay, but workers also call transaction
  directly. `_audit` accepts an actor string, event kind and arbitrary payload;
  an event label or payload claiming a GM identity is not authorization.
- `services/m2_game.py::event` calls incarnation preparation, Consume/Wyvern
  hooks, then appends an event, then applies Doctor, Martyr, Insurance, neural,
  compliance and other lifecycle hooks. A comparison before these hooks misses
  final effects. SQL writes after event() also need the final transaction guard.
- `engine/m2.py::GameState` stores a campaign JSON object, not actor-owned rows.
  `facts` is a list of dictionaries; source-specific functions decode records.
  Ownership is not inferable from matching an arbitrary numeric string.
- `database/m2_schema.py` binds actions and choices to account IDs, not original
  incarnations. Receipts and outbox rows point to actions; locks point to actions
  and channels. `m3_required_work` has owner and subject accounts plus opaque body
  data. None alone establishes the full set of affected original actors.
- `delivery/m2_worker.py::deliver` commits sending before awaiting publish, does
  not check that the sending UPDATE matched its claim, and cannot roll back a
  publish when the later acknowledgement transaction fails. `acquire` and
  `restore` similarly call set_overwrite outside the write transaction.
- `services/m3_easy_target.py::_finish` correctly refuses completion with any
  pending choice or incomplete Reaction. Shelving must not alter that meaning.

## Required durable authority

Add a migration-backed current availability table keyed by campaign and exact
ActorRef(kind, entity, incarnation), with monotonic availability generation,
record revision, phase, request ID, owning human, and last transition event.
Use explicit quiescing, active, resume-review and resumed phases. Requests alone
remain intake. Keep transition history private and append-only. No reason text.

Activation transaction must re-resolve current membership and configured human
facilitator from stored configuration, verify expected request revision and exact
current original ActorRef, and reject a replaced or ambiguous incarnation. A
player request is not GM activation and a GM proposal is not player consent.
Validate the command principal using the existing authenticated viewer path.
The authority object is internal to the authorized command; it cannot come from
metadata, an event kind, a user-provided actor string or arbitrary SQL rows.

In one transaction append a typed transition event and compare-and-set the current
row, recording the exact prior revision, new revision, original actor, request,
reviewer and current configuration event. Event identity must be unique and bound
to that transition and command, not merely present somewhere in the campaign.
Reject direct availability changes lacking this binding at final validation.
Revalidate current authority before idempotent replay as intake already does.
Resume must leave the original source blocked if its dependencies cannot be
revalidated; it must not restore a whole old campaign snapshot.

## Exact projection contract for the first supported slice

Start with original NPC Easy Target use and one deferred original cohort nominee.
Before coding, enumerate its allowed commands and every changed field for each.
A command adapter produces exact before/after typed effects and resource keys;
that declaration is checked against the actual final transaction, not trusted.

Protect the absent actor's entire PilotSheet and its existence/incarnation;
Handler shelving is unsupported in this first slice. Protect actor-bond edges
with either endpoint equal to that ActorRef, helpless conditions with either
subject or foe equal, and original physical placement plus vessel/control links.
Protect all ownership, custody, archive, identity, consequence and obligation
records referring to that original actor through each domain's typed accessor.
Unimplemented domain accessors mean its changes are rejected, not ignored.

For Easy Target, use the existing typed records(), Session, Reaction, NpcUse and
UseCohort models. Protect the nominee's Reaction, its original choice and source
links, all its response/receipt rows, and its required-work records. The shared
Session/cast, primary Reaction and NPC use are dependencies, not wholly owned
by the nominee. A validated primary-use ending may update only its enumerated
fields, while preserving the nominee's incomplete Reaction and unsubmitted
choice byte-for-byte. Do not create UseCohort(outcome='missed') on their behalf:
that remains their own normal response after return. New shared dependencies or
changed original identity fail closed.

Classify every GameState field explicitly: actor-local typed records, supported
shared records with field-level rules, or unsupported-to-change. New model fields
must fail the completeness check. For facts, parse only registered exact kinds
with their real domain codecs; unknown facts must remain unchanged. No guessed
JSON recursion, prefix ownership, blanket world exclusion or permission to change
an entire other player's sheet without checking cross-actor effects. Facts that
are unchanged need no invented ownership classification. Unknown changed facts
block the command.

Operational projection uses exact action/choice/work IDs and resource relations,
not global snapshots of every table. Track actor incidence for actions (including
indirect targets), choices, work, receipts, scene/cast resources, locks, source
pauses and outbox jobs. Shared rows need per-operation field policies. Append-only
history and command receipts are allowed only as the verified projection of the
same authorized operation, never as arbitrary exempt inserts. Safety pause and
private readback remain separate authorized control paths; no exemption for an
arbitrary event that happens to be named safety or shelving.

## Transaction integration and bounded cost

At transaction entry, read the campaign's indexed current active/quiescing rows,
not replay intake history. No active shelf means no projection work. Scope the
transaction to its own campaign; malformed data in another campaign must not
block it. Register schema version and all mutable table/column handlers; unknown
schema fails shelf activation rather than silently widening exclusions.

At SQL execution, capture changed table/primary-key identities using a
transaction-local write journal or equivalent database-enforced mechanism that
covers updates, deletes, inserts and SQL-only service writes. No string parsing
of SQL as a security boundary. Final validation checks actual rows against the
operation's verified write set and actor incidence, after all hooks and writes,
before commit. Unregistered writers cannot mutate with a shelf active. This is
a cooperative application boundary; migrations/admin raw writers remain offline
and outside the gameplay claim. Explicit early commits must be prohibited in
application transactions, not assumed impossible.

The current campaign JSON means final canonical validation still requires a
comparison of the loaded GameState; do not advertise constant cost. Avoid
additional full historical-table scans. Establish a measured maximum supported
state/write-set size, fail safely above it, and index source/actor lookups. A
truly actor-sized canonical check requires moving classified state into indexed
projections or recording verified typed deltas at every mutation entry point.

## Worker fencing: activation is a drain, not a toggle

Add actor/resource incidence and availability generations to every external job.
A worker acquires an effect permit transactionally, checks current claim token,
generation and resource ownership, and verifies an UPDATE actually matched
before any network mutation. Quiescing prevents new affected permits; unrelated
jobs continue. Existing permits may still perform effects: therefore do not call
the actor frozen until every affected permit has a known reconciled outcome.

Expiry alone is not proof an old worker stopped. Discord does not enforce our DB
fence token. An expired/uncertain permit keeps activation pending until its
worker is known terminated and the remote outcome is reconciled. Never turn a
local lease expiry into permission for a competing send or lock rewrite. A
process-local mutex alone does not cover restart or multiple workers.

After draining, the activation transaction rechecks original identity, resource
versions and the parked-source plan, then sets active and advances generation.
Jobs admitted before quiescing must acknowledge/reconcile without changing the
protected gameplay projection; they cannot be rejected after a remote mutation
and silently forgotten. Resume runs the same generation discipline. Recovery
screens must preserve private payloads and avoid revealing absence to a channel.

## Parking integration contract

The separate root-lock prerequisite is useful but does not supply parking.
Parking needs a durable original-source relationship and distinct paused work,
not complete/aborted action states. Preserve choices, rolls, reservations, cast,
scene and required work. A validated park plan must prove active participants'
remaining work independent, record precise lock transfer/recovery dependencies,
and be committed with the availability transition after worker drain. Rejoin
revalidates those originals before presenting the still-owned choice. Never
remove absent actors globally from pending() or teach finish() to invent consent.

## Delivery gates

Implement in this order: indexed authority/transition schema; typed effects and
SQL write journal for the narrow slice; worker permits/drain/reconciliation;
park/resume integration; independent review; then enable activation separately.
Root-owned synthetic checks must demonstrate (1) independent actor progresses,
(2) direct/indirect/SQL-only protected change fully rolls back, (3) legitimate
shared source ending preserves absent work, (4) stale identity/reconfigured GM
cannot activate or replay, (5) in-flight remote job prevents activation until
reconciled, (6) return exposes original choice without new roll or invented answer,
(7) unknown changes block and private data remains private. Passing an isolated
classifier test is not acceptance of the integrated workflow.

No safe bounded implementation of this full boundary was established in this
assignment. The concrete prerequisites above span canonical, operational and
remote effects; retaining SHELVING_UNAVAILABLE is the correct current behavior.
