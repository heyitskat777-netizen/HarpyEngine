# Exact canonical comparison connected to captured SQL evidence

Unused prerequisite on v35. No runtime producer, availability transition, activation,
worker or UI is wired. It is not permission to commit a command or proof that a
player has been frozen. Protected references are comparison inputs, not durable
availability authority. The returned evidence explicitly has authorization=false.

## Concrete supported comparison

`engine/p1_canonical_projection.py::verify_heat_spend` validates before/after
GameState JSON and requires one original Pilot's existing spend_heat cost, one
subject sheet revision increment and one canonical revision increment. The existing
spend_heat rule decides valid spending, including spending all when holding five
or more. This adds no new rule interpretation and does not authorize the cost.

The subject and every protected reference must resolve to the same original Pilot
in both snapshots, including the sheet's owner and incarnation. Missing, replaced,
non-Pilot or protected subjects reject. Complete expected-state equality then
requires every other Pilot field, every other sheet, every shared/global field,
unknown fact, relationship, choice and obligation to remain unchanged. No recursive
account-ID search or guessed ownership is used. Duplicate/non-finite JSON rejects.

Explicit GameState and PilotSheet field inventories reject new top-level/sheet
fields pending classification review. Nested objects are compared in full; no
nested field is exempted from equality. Whole-state parsing and comparison are not
actor-sized or constant-time. This is one narrow canonical substep, not acceptance
of any existing complete gameplay command or a generic Heat setter.

`services/p1_canonical_guard.py::verify_captured_heat_spend` connects that comparison
to actual collector output: precisely one UPDATE to this campaign's m2_state row,
unchanged primary key, known row columns and SQL revisions matching both canonical
bodies. Any additional SQL write, including command/event/receipt/outbox/choice
writes, currently rejects. Such writes need authenticated typed source adapters;
none are broadly exempted based on an event label. Insert/delete/replacement and
other campaign changes also reject.

## Trust and integration boundaries

The comparison itself does not mutate input or storage. Callers must obtain the
before/after rows from the still-live write collector and validate before committing.
A fabricated Change tuple or declared amount is not authenticated evidence. Real
source authorization, current membership/original-profile proof, player-owned cost
choice and durable protected-actor generations remain external prerequisites.

The SQL collector must be installed at source transaction entry with exclusive hook
ownership, safe transaction lifetime and managed savepoints. Captured evidence plus
this narrow checker still does not establish full transaction admission. No command
currently satisfies this one-row SQL shape with its required audit/idempotency
records, so no existing runtime command is newly allowed while another actor is
absent. Future source adapters must prove those extra operational writes and final
canonical effects rather than disabling this fail-closed check.

Safe shelving also still requires indexed availability transitions, complete
actor/resource incidence, external-worker permits/drain/reconciliation, parked shared
source preservation/rejoin and independent end-to-end acceptance. Do not activate a
freeze from these comparison results. Existing activation/reserve rejection remains.

## Candidate and checks

Candidate: harpyengine-p1-canonical-guard-20261110. v35 collector source, tests and
document hashes were checked against the revision35 package before copying. v34
was preparation-only; no separate runtime source was omitted. Four new owned files:
two source modules, one focused test module and this document. Root's first run
found a collector compatibility defect against historically migrated databases.
Two existing collector files now also change: name-based column shape validation
and migration-created coverage. Historical migrations remain untouched.

Worker scoped Ruff and mypy --follow-imports=silent on both source modules pass.
Worker did not run pytest. Root minimum:

    PYTHONPATH=src /workspace/scratch/1003c11eb181/harpyengine-p1-adapter-20261109/.venv/bin/python -m pytest -q tests/rules/test_p1_canonical_guard.py

Two cases authored: source-shaped SQL updates inside real capture accept the exact
independent cost comparison, while protected canonical changes, unknown shared
facts, SQL-only member changes, protected-subject costs and replacement identities
reject; all transactions roll back and private values stay out of errors. Synthetic
Heat fixture is not an authenticated production spend. A separate field-inventory
case requires review for a newly added canonical field. Root execution, independent
review and final exact-candidate global/human gates remain pending. No bot, deployment,
merge, publication or access-denial workaround.


Root first comparison run: 1 failed, 1 passed. The failure was collector schema
admission, before the comparison ran. A read-only inspection of the failed fixture
confirmed only physical column order differed for m3_required_work and
creation_bond_revisions: ALTER TABLE appends columns whereas create_all groups them.
Capture now compares the complete set/count of named columns, preserving exact PK
shape and missing/unknown-column/BLOB rejection. Generated SQL already names every
column explicitly; physical column order has no classification meaning. The existing
capture rollback/replacement test now runs against both metadata and migration
schemas. No historical migration was modified. Revised root tests/review are pending;
initial successful checks do not cover this collector correction.
