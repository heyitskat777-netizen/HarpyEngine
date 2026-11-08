# M3 integration regression boundary

Status: **FULL RUN FAILED; ALL REPORTED FAILURES PASS FOCUSED RECHECKS**.
M3 remains **RULES_SUBSET**; bot off. This is an integration
baseline before the next shared-core migration, not a final M3 acceptance claim.
The current source checkpoint and focused evidence are linked from
[M3_CURRENT_QUEUE.md](M3_CURRENT_QUEUE.md).

The earlier stop-at-regression boundary was honored. The owner subsequently
authorized continuing the queue until M3 is ready for play-testing, including this
baseline and its repairs. Frozen source `eb7eec5` completed one full process:
**2,562 passed, 3 failed, zero errors/skips in 1781.24s**. Global Ruff/format, types
(643 source modules), isolated CLI health, registry/planning/repository checks
passed. Two minimal production repairs address all three failures; seven focused
checks pass. Full-suite results after those repairs remain **NOT_RERUN**, not green.
Exact artifacts are in the current M3 acceptance report. Resume bounded gameplay
delivery after integrating these repairs; preserve final-candidate verification.

## Why this is the next boundary

The next ordinary Marriage workflow cannot be implemented by changing only an
award or Inbox card. It changes shared Status while the current unique `order`
also represents the physical roster. It must route seven Permission grant paths
and more than twenty direct charge/loss paths before their immutable receipts,
without changing the physical beneficiary or treating a controller as a character.
`charge_standard` currently has no service callers, so changing that helper alone
would miss real purchases. Punishment allocation must preserve the original
cause while changing the subject before the instruction is issued.

The previous complete-suite evidence predates this integrated source. Later
focused checks and the repair package's segmented results are useful scoped
evidence, but do not establish one coherent current regression baseline. Running
that baseline before the shared migration separates existing integration failures
from future Status, wallet and discipline changes and avoids interleaving both.
This is the specific integration concern permitting an earlier broad run under
the development workflow; final M3 candidate verification is still required later.

## Executed baseline and future verification

The following commands ran against the frozen baseline with the installed locked
environment and synthetic fixtures. Results and exact scope are recorded in
`var/m3-pre-marriage/` and `var/m3-pre-marriage-regression.xml`. Future broad runs
need a relevant failure/change or the final M3 candidate:

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/pytest -q --junitxml=var/m3-pre-marriage-regression.xml
```

Retain the established CLI, rules-registry, original planning and repository checks
from CI. Use isolated temporary databases for migration/backup/rebuild tests; do
not migrate or reset the live/private campaign. Do not silently substitute
segmented runs for a single full result; record any execution limitation explicitly.
Existing environment-specific runner approval needs do not authorize live bot use.

If failures occur, classify the actual failure and repair the smallest relevant
source/fixture issue. Repeat affected checks, then re-establish the integrated
result when warranted. Do not weaken a gate or classify a missing rule as passing.

## Work after that baseline

Release explicit file ownership for the ordinary Marriage workflow: shared Status,
pre-receipt financial chooser/wallet separate from physical recipient, original
Permission-flow proof, allocated Punishment sources and actual caught-Flirt
witness evidence. Reuse the frozen source contracts; no post-receipt pooling,
account aliases, automatic dialogue/intimacy or passive-chat discovery. Keep
unusual source/body adapters explicit and retain all independent/player gates.
