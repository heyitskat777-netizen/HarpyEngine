# Guarded original Pilot enrollment

Dependency: exact v44 immutable availability ledger, v42 guarded request source,
and retained v41 integration evidence. No schema or migration changes.

The callable service enroll_current_pilot authenticates the viewer through current
game membership/access and resolves the current original Pilot and saved identity
proof. Its expected ActorRef is only a stale-view check. It cannot enroll another
player, mistake a replacement actor for an old one, or resume a draining actor.
No UI, startup auto-enrollment, GM proxy or bulk enrollment route is installed.

Within the guarded BEGIN IMMEDIATE transaction, enrollment plans exactly one
active generation-1 row, one private original-proof audit event and one idempotency
receipt. All captured writes must match. Hidden side effects roll back the whole
source. Same-key replay still reauthenticates and checks current active state;
a new key for an already active actor writes only its exact receipt. A draining
actor rejects both paths. Committed-cleanup and uncertain commit outcomes retain
explicit no-blind-retry guidance.

The shared exact audit/receipt validator now accepts a source kind defaulting to
the unchanged intake kind. Enrollment supplies its fixed service-owned kind, not
caller input. No gameplay writes are exempted or authorized by event labels.

This closes the missing authenticated local enrollment producer only. Canonical
storage and authenticated adapters remain trusted. A manually inserted database
row is not independent cryptographic provenance. Existing gameplay does not yet
enforce availability everywhere; no current actor is frozen. Draining producer,
worker admission/drain/reconciliation, source incidence, parked choices and safe
rejoin remain required. Active enrollment neither consents to shelving nor grants
a remote dispatch permit. Internal outcomes contain private proof, not UI copy.

Focused test authored, worker Ruff/mypy passed; root owns pytest and independent
review. No full regression, deployment, bot activity or publication.
