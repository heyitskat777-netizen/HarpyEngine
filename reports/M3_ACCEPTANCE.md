# M3 acceptance — scoped, implementation not yet certified

Status: SCOPED_NOT_IMPLEMENTED / RULES_SUBSET. Date: 2026-11-04 UTC.

The owner authorized beginning M3 and requested its completion requirements. The
initial planning delivery (`4d2813b`) is the additive work order `docs/work_orders/M3_RULES_COMPLETION.md`,
M3A–M3H sequence, updated active instructions/roadmap and the acceptance plan in
`docs/acceptance/m3_rules.json`. That planning-only commit left application source,
live data/policy, the running bot and environment configuration unchanged.

The plan preserves all 14 original M3 regression cases, all ten source-plan RUL
checks and adds eight coverage/integration/acceptance requirements. Every case is
NOT_RUN with empty execution evidence. No existing M2 evidence has been promoted
to independent certification or used to claim M3 mechanics pass.

Read the actual official PDF/sheets for M3A; the historical handoff page references
are approximate. No complete rule/Play/branch count has been established yet.
M2's previously verified 433 tests describe its source baseline; no new application
tests are claimed for this documentation-only planning step.

Required before M3 completion: full agreed source coverage, reducer/fixture and
service/UI tests, M3/RUL regressions, migration/replay/isolation/recovery evidence,
independent source/code review, human Discord acceptance and owner sign-off.
The original handoff remains unchanged; private PDFs/engine/data stay outside Git.

Planning checks executed:

- Additive acceptance-plan validation: 14 historical M3 cases + 10 RUL checks + eight
  additional requirements, unique IDs, all NOT_RUN and empty evidence: PASS.
- Original handoff verifier: 34 required files, 86 planned cases, four schemas and
  four synthetic fixtures: PASS (planning only).
- Publishable-file check: 241 files, all 40 manifest entries intact, zero findings.
- `git diff --check`: PASS.

No application test run, live interaction test, migration or deployment was needed
for this planning-only change. Human/independent M2 and M3 acceptance remain open.


## Owner-requested Discord lifecycle presence

The owner then requested a visible Discord status for running version, restart and
offline state. This operational addition does not complete any M3 rules case.

The bot now identifies with a starting custom activity, publishes **Running v0.1.0**
on READY, and restores it after reconnect/resume. The version is read from the
actual application package. A controlled SIGTERM restart publishes **Restarting**
and a normal graceful close **Stopping**, with the version. Shutdown remains safe
if presence publication fails or times out. The bot publishes no campaign/private
state and needs no privileged presence intent. Discord controls the offline indicator
after disconnection; a stopped/crashed process cannot send an offline activity.

Validation executed:

- Focused presence + read-only bot suite: **28 passed in 0.57s**.
- Full suite: **438 passed in 36.61s**, no skips/failures; five new lifecycle tests.
- Ruff: all checks passed; format check: **162 files** formatted.
- Mypy: no issues in **87 source files**.
- Publishable check: **243 files**, 40 original manifest entries intact, zero findings.
- Frozen-source startup check passed; a private backup was created and the bot was
  restarted onto the tested frozen presence build. No migration or policy edit.
- Live output: **HarpyEngine presence: Running v0.1.0** followed by Gateway READY.
  This verifies the outbound presence send, not human Discord-client rendering.
- Read-only REST: **13 guild command groups, zero global commands**; process
  readback: exactly **one bot**. Live schema remains **0011**, integrity `ok`,
  zero foreign-key errors, and gameplay release approval remains absent.

The initial transition from the old build could not show Restarting because that
build had no presence feature. Future controlled restarts use the new handler.
A future live shutdown/reconnect display and human mobile/desktop rendering remain
unverified; their offline lifecycle/failure behavior is covered by tests. M3 rules,
independent certification and M2 human acceptance remain pending. No environment
configuration was modified or published. Private runtime/backup artifacts stay ignored.
