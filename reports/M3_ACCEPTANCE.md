# M3 acceptance — scoped, implementation not yet certified

Status: SCOPED_NOT_IMPLEMENTED / RULES_SUBSET. Date: 2026-11-04 UTC.

The owner authorized beginning M3 and requested its completion requirements. The
initial delivery is the additive work order `docs/work_orders/M3_RULES_COMPLETION.md`,
M3A–M3H sequence, updated active instructions/roadmap and the acceptance plan in
`docs/acceptance/m3_rules.json`. Application source, live data/policy, the running
bot and environment configuration are unchanged.

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
