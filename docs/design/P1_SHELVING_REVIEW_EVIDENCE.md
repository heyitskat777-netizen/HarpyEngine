# Transaction-current shelving review evidence

This unused service is an authority preflight prerequisite, not an actor
availability authority, activation, freeze or dispatch permit. No caller/UI is
wired and no gameplay state, SQL row, command, audit event or outbox job is written.

`ShelvingReviewService.inspect` starts a real SQLite read transaction for a
consistent private snapshot. `inspect_transaction` can be used inside an existing
source transaction, but rejects a connection with only SQLAlchemy's deferred
logical transaction. Both resolve the authenticated viewer through current campaign
membership and configured human facilitator before accessing the target request.
No inspection result can be submitted as authorization to another method.

The service resolves the latest exact saved intake event, requires its expected
pending revision, validates original Pilot/owner/proof shape and original snapshot,
then re-resolves current active membership and canonical incarnation proof. A
previous actor's request remains readable/withdrawable through existing intake but
cannot yield current actor review evidence. A GM proposal stays distinct from the
player's own request. Handler/NPC authority remains unsupported. A same-actor profile
revision advance is not treated as a new person; the saved snapshot must still exist.

The immutable typed result includes exact request event/revision, original actor,
current identity proof, reviewer/configuration event and canonical game revision.
`availability_authority` is literally false. It is a private, snapshot-local result,
not a durable generation, lease, permit or cached capability. A later mutation must
resolve current authority again within its own source transaction. Ordinary unrelated
changes after the read are not blocked or rolled back by this service.

Trust boundary: the existing authenticated adapter supplies GuildViewer. Arbitrary
player-authored metadata must not construct that principal. This service treats
existing canonical records and source-event storage as the cooperative application's
records. It does not prove arbitrary SQL writers trustworthy, authenticate the
transaction that originally authored intake, or grant actor-resource authority.

Still required before actual availability transitions: indexed current availability
and append-only transitions; source-specific complete actor/resource incidence;
canonical and SQL-only final transaction guards; worker permit/drain/reconciliation;
parking/rejoin that preserves original choices; and independent end-to-end acceptance.
No transition to quiescing/active/resumed is provided. Existing activation rejection
and journal reserve rejection are unchanged.

## Scope and evidence

Base is the v29 shelving UI copy. Verified its three UI output hashes and all eight
v27 hardening output hashes against their manifests before making the isolated copy.
Changed Python: one new service, one new focused test module, and additions to the
existing real Vatgrown death/replacement test. No shared core or intake implementation
was changed. Worker Ruff lint/format passes; pytest intentionally left to root.

Root minimum:

    PYTHONPATH=src /workspace/scratch/1003c11eb181/harpyengine-p1-adapter-20261109/.venv/bin/python -m pytest -q tests/rules/test_shelving_review.py tests/rules/test_vatgrown_death.py::test_actual_vatgrown_death_fresh_native_activation_and_original_other_owned_notice

Coverage authored: current facilitator read-only evidence, current reconfiguration,
stale/withdrawn request rejection, snapshot transaction requirement, active target
membership, explicit GM proposal distinction, and actual replaced actor rejection
with successful review of the real fresh actor. No full regression or live test.
