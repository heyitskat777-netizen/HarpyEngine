# Development workflow and M3 delivery path

Owner-approved usage policy, 2026-11-05. This is the current execution policy;
it supersedes older four-agent defaults and exhaustive per-change test plans.
The M3 scope, official rules authority and release gates remain unchanged.
The owner's November 5 workflow handoff reaffirms this policy; its `12a08c2`
reference is historical. Preserve newer commits, local work and completed handoffs.
Reconcile only relevant changes; do not restart a source audit or completed unit.

## Staffing and work limits

- Use at most two implementation sub-agents by default. Root owns shared routing,
  integration and the current integration deliverable.
- Give each agent one named workflow, explicit file ownership and a small API
  handoff. Do not duplicate source investigation or edit the same shared region.
- Use an extra agent only temporarily for clearly independent work with an
  expected saving in total effort. Four agents are no longer the standing setup.
- Finish, hand off or explicitly block an assignment before opening another.
  Agents stop after their deliverable rather than automatically expanding scope.

## Fixed deliverables

Before coding, record a short contract in the assignment or existing handoff:
normal player flow; actual sheet/world effects; files and dependencies; one
completion demonstration; explicit unsupported cases. Use existing reducers,
services and native Discord controls. Add infrastructure only when the named
workflow cannot work correctly without it.

Distinct printed result branches and their immediate consequences are normal
outcomes and must each have focused evidence. They are not optional edge cases.
Do not multiply those branches across speculative actor/lifecycle combinations.

Implement required normal outcomes and immediate consequences. Do not expand into
speculative role combinations, rare lifecycle intersections or general frameworks.
Record those gaps with their existing fail-closed boundary. Deferral does not make
a required M3 rule complete; required gaps stay in the milestone backlog.

## Current delivery order

| Order | Assignment | Completion boundary |
|---|---|---|
| 1, parallel | Retained Kicked Puppy | Retained Dampener frozen. Extend only the next real consumer through exact original paid source/Swap chain and actual Flirt effect; preserve source state and production review gates. |
| 1, parallel | Supply Drop | Genuine award/spend frozen. One actual award acquisition and both once-per-Mission branches: repair and real temporary Frame equipment delivery/expiry, with actual required consequence guards. |
| 1, root | Source/CI integration and next Budget consumer | Freeze retained Dampener, genuine Void awards and real NPC departures. Select the next dependency-ready Budget Endgame workflow, with exact original source/affected-player choices and mandatory consequences. |
| 2 | Remaining required gameplay systems | Select the next dependency-ready whole workflow from M3_REMAINING_WORK.md and M3_COMPLETION_AUDIT.md. Freeze its contract, reuse implemented dependencies and complete it before opening unrelated work. |
| 3 | M3 review candidate | Account for required core scope, complete expected gameplay flows and final integrated checks; provide a concise player-test checklist and stop for owner review. |

Physical and Lifecycle agents hand off existing work and stop; their completed
code and evidence remain available. No work is discarded to reduce concurrency.
Ancillary playbooks remain deferred. AI/M4, deployment and publication are outside
this development path. The bot stays off.

## Verification budget

- Reuse existing tests. Run a small focused selection for the changed workflow's
  expected behaviors and base functionality. Avoid exhaustive actor/tier matrices.
- Retain narrowly relevant checks where changed code risks saved-state loss,
  duplicate rolls/charges, privacy disclosure or bypassed player consent.
- At a coherent handoff, run formatting/lint over **all changed Python files**,
  including every shared interface and test file, plus applicable source type
  checks. Feature-only static scopes are insufficient. Fix reported defects;
  reuse passing evidence until a relevant change or concern invalidates it.
- Do not delete or weaken existing tests to obtain a passing result. New expected
  gameplay outcomes still need meaningful verification, not mirrored assertions.
- Reserve the full existing regression and global static/migration/privacy checks
  for the final M3 review candidate. Run earlier migration or privacy checks only
  when the current change actually affects those boundaries. Further broad runs
  need a relevant failure, change or unresolved integration concern.
- A focused pass is scoped evidence, not full regression or independent approval.
  Human play-testing remains separate; unusual combinations carry less assurance.

## Continuous integration

Keep the existing `offline-foundation` job/check name and release gates. The CI
workflow uses an explicit, short pytest selection in `.github/ci-tests.txt`; update
it at each bounded integration handoff with the required normal branches and
affected integrity checks. This is a list of existing pytest paths/node IDs, not
an automatic dependency-selection framework. A missing/empty selection fails.

Normal pushes/PRs run that focused selection and static checks on the changed
Python files, including tests and shared modules. Ordinary Markdown under
`docs/`/`reports/`, README and AGENTS skips gameplay tests; runtime rules, JSON
contracts, configuration, Python changes, deletions and moves across that boundary
do not qualify as ordinary documentation. Runtime-registry, original planning
and publishable/manifest checks remain. Branch concurrency cancels superseded
push/PR runs for the same source branch; it does not reuse a completed result.

For the final M3 candidate, run the workflow manually with `full_suite=true`
against the exact candidate, or run the full local commands if dispatch is not
available on that branch. Dispatch availability depends on the workflow existing
on GitHub's default branch; do not change `main` merely to expose it. Full mode
runs global lint/format/types, the complete pytest regression and the same CLI,
contract and repository checks. The focused job's green result never substitutes
for this required final verification or for independent/player review. No branch
protection or required-check settings are changed by this workflow adjustment.

Required local final-candidate commands (run against the frozen source; retain
CLI, registry, planning and repository checks from CI as well):

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/pytest -q --junitxml=var/m3-final-candidate.xml
```

CI artifacts record the checked commit, comparison base and focused/documentation/
full scope alongside actual JUnit results. Latest remote failure and repairs
belong in the existing acceptance report; do not call local checks remote CI.

## Context and reporting

Keep one compact handoff per assignment: changed files/API, completed behavior,
exact validation result, remaining gaps and next action. Store private details
under ignored `var/`; public summaries contain sanitized facts only. Read the
handoff and changed code when resuming rather than repeating whole-book or whole-
repository audits. Reread source only for a new rule or genuine ambiguity.

Consolidate public acceptance/ruling updates at completed workflow boundaries.
Preserve historical test evidence without copying it into every status report.
Tie evidence to its exact commit or an ignored reproducible source snapshot with
changed-file hashes. Never attach an older full-suite result to newer edits.

Use this compact status when reporting a handoff:

```text
Checkpoint: <commit or reproducible source snapshot>
Completed: <named workflow and supported boundary>
Validation: <exact command, result, focused/full scope>
Active: <assignment and owner>
Blocked or unsupported: <specific dependency or remaining behavior>
Next: <one concrete action>
```

Use brief milestone/blocker updates and avoid repeated polling or large outputs;
continue necessary user-facing progress communication during longer work.

Track finished named workflows, active work and remaining systems. Do not convert
test counts, registry counts or unequal units into percentages or credit promises.
