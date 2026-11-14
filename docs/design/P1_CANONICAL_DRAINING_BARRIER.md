# Conservative canonical draining barrier

Dependency: reconstructed v46 (v41 combined guards, v42 request, v44 availability,
v45 stale delivery claim, v46 enrollment), every changed input/output hash checked.
This is a partial persistence barrier, not a complete actor freeze or gameplay path.

Migration 0020 installs fail-closed INSERT, UPDATE and DELETE triggers on m2_state.
Any draining epoch in a campaign blocks that campaign's entire canonical row,
including same-value writes, movement between campaign keys, OR REPLACE, and
explicit occupied-rowid conflicts with recursive triggers disabled. Old draining
incarnations remain blockers: there is no safe rejoin/retirement lifecycle yet.
Unrelated campaigns and merely active enrollment are not blocked.

GameService.event rejects canonical state writes before identity preparation,
audit/history and follow-on effects, with a private generic WorkflowError. SQL
triggers remain authoritative for alternate/direct writers. Ordinary transaction
rollback preserves pending work; the guard does not complete, cancel or rewrite
choices. Private intake request/withdrawal remains possible without canonical
mutation, as the focused test demonstrates. Migration and metadata use identical
frozen trigger SQL; downgrade refuses to remove the barrier.

Limits: this does not guard every side table, character snapshot, source choice,
roll, outbox or external worker. Operations may perform non-database actions before
reaching persistence; this guard cannot undo them. A caught SQL statement error
is not proof the caller rolled back all preceding writes. Future draining admission
must require complete source coverage, worker admission/drain/reconciliation,
resource incidence and preserved parked choices. No production draining producer,
new UI activation or frozen state is added. Do not call this selective shelving:
until finer incidence validation exists it deliberately rejects unrelated canonical
changes within the same campaign too. Existing safety pause remains independent.

Tests authored: metadata/migration raw write and replacement cases; actual existing
canonical event writer rollback after authenticated enrollment and synthetic drain,
then retained private intake withdrawal. This is not a full gameplay/freeze test.
Root owns pytest; no worker test execution or full regression.
