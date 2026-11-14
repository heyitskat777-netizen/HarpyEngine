# Durable Pilot availability epochs, preparation only

Dependencies: verified v42 request source plus retained v41 integration test.
Migration 0019 adds an empty, indexed, WITHOUT ROWID epoch history. It does not
backfill active actors or infer availability from membership, intake or consent.
No runtime enrollment/transition producer is implemented. Existing gameplay does
not call this gate, so this is not an enforced freeze or a release-ready feature.

Exact campaign, original Pilot owner and incarnation form the actor key. Missing
history fails closed. Only synthetic/trusted initial active generation 1 followed
by draining generation 2 is representable. Rows cannot be updated, deleted or
replaced, even with recursive triggers disabled. No frozen/shelved/rejoin state
exists. A previous incarnation never grants the replacement actor availability.
Draining is not proof of worker drain, parked work or completed freeze.

The transaction-local read gate reauthorizes membership/game access and resolves
current original actor proof before checking the exact expected epoch. Its return
value is a private fact, not a reusable permit. A new source/claim must re-read in
its own transaction and still authenticate producer, classify all actual writes,
and establish resource incidence and worker safety. Canonical database storage
and the authenticated viewer adapter remain trusted, not hostile SQL/Python.

The immutable ledger has no authenticated production writer. Do not fabricate
initial active records in application code; current callers must remain disabled
until the source and whole-workflow admission policy exists. No UI activation,
external dispatch, parked-choice mutation, dice or player commitment is added.
Downgrade fails closed rather than discarding retained availability history.

Worker authored targeted tests; root owns execution. A migration-path test and
collector compatibility check are required because the capture inventory includes
the new modeled table. Full regression and final privacy/restore gates remain open.
