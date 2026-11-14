# Guarded original-owner withdrawal and current-facilitator decline

This connects v38 transaction mechanics to a real existing private control source,
not a synthetic permissive callback. It does not freeze a player, park a source,
release a cohort, grant journal dispatch, or change gameplay choices/obligations.
Activation still takes the existing unavailable path. Request creation remains on
its existing intake path; only withdraw/decline are routed through this guard.

## Authority and operation

ShelvingService.change routes withdrawal and decline to p1_guarded_intake. The
adapter starts a dedicated guarded source transaction, rechecks the authenticated
GuildViewer's campaign membership, and resolves owner/current-facilitator authority
from storage before command replay. Decline checks the current facilitator before
reading the request. An original player may still withdraw their previous actor's
request after a genuine replacement. No current-actor activation authority is inferred.

The request hash and saved outcome format match the previous _write contract.
Matching replay performs no writes but still revalidates current authority. A new
key requires the exact pending revision. The source creates precisely the existing
private intake event, campaign revision increment and command receipt. It reuses
GameService.event with the original KIND/RULESET and does not invent gameplay audit
or bypass any original player request/proposal distinction.

A frozen internal plan binds the current campaign snapshot, reviewer, command key,
request digest, exact updated payload and event ID. Final validation consumes actual
collector output and requires exactly that campaign update, event insert and command
insert in order, with correct keys, private visibility, ruleset and canonical payload.
No generic audit exemption exists. Any additional actor/choice/member/outbox write,
extra event or altered source payload rejects the entire transaction. Unchanged
private source fields and original actor proof remain private and preserved.

Post-commit cleanup failure reports the intake as committed and directs readback,
not resubmission. An uncertain commit reports uncertainty and prohibits a new-key
retry until saved state is checked. Precommit classification rejection reports no
committed intake change. No automatic retry or alternate unguarded write path exists.

## Trust and limits

Transport authentication and canonical/event storage are trusted as elsewhere in
this app. The adapter does not establish database-administrator isolation or prove
arbitrary historical SQL edits authentic. It is a reviewed source-specific boundary,
not a general-purpose adapter for all gameplay operations. It requires the existing
migrated file-backed SQLite database; in-memory databases cannot be reconnected by
the dedicated transaction owner and fail explicitly rather than falling back.

The actual mutation is to intake control history, not a gameplay freeze. Remaining
freeze requirements include durable current availability/generations, authenticated
complete actor/resource incidence, canonical/SQL policies for gameplay, worker drain
and remote reconciliation, parked source/rejoin, and exact-candidate/human acceptance.
No permission is added to expose private proofs, choose for absent players, waive
pending work, run the bot or activate shelving.

## Isolated scope and checks

Candidate: harpyengine-p1-guarded-intake-20261110, copied from v38 after verifying its
three guarded-wrapper output hashes. That source retains the verified v37 dependency
chain. This lane changes only p1_shelving.py dispatch, new p1_guarded_intake.py, a
new test and this document. Collector/wrapper/journal files are untouched. Concurrent
managed-savepoint work is separate and still needs explicit delta integration.

Worker scoped Ruff and targeted mypy pass. Worker did not run pytest. Root proposed
minimum (all are directly affected existing controls, plus one injected-source test):

    PYTHONPATH=src /workspace/scratch/1003c11eb181/harpyengine-p1-adapter-20261109/.venv/bin/python -m pytest -q tests/rules/test_guarded_shelving_intake.py tests/rules/test_shelving_intake.py tests/rules/test_vatgrown_death.py::test_actual_vatgrown_death_fresh_native_activation_and_original_other_owned_notice

New coverage checks actual withdrawal, exact-once event/receipt and authorization
before cached replay. Injected member mutation and changed player provenance must
roll back every table; no dice/canonical state changes are permitted. Existing tests
exercise native withdrawal, current-GM decline/revocation, stale requests, unchanged
activation refusal and historical actor withdrawal after real replacement. These
are authored/proposed checks, not passed evidence. Root execution, independent review,
full release gates and live/player acceptance remain pending. No broad regression,
push, merge, deployment, bot startup or denied-access workaround.
