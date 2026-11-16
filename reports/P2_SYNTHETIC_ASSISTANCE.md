# P2 synthetic assistance — bounded backend checkpoint

Owner instruction authorizes this increment and sanitized development pushes
before P1 human acceptance. It does not certify P1, expand gameplay approval or
authorize deployment. Last verified live source remains v0.1.4 at
`fe47d7ef0b558a1106f5dc48b25c277aff5f875b`; this task did not inspect or alter its
process, policy, database or frozen source.

## Reconciliation and scope

Execution worked in `/workspace/HarpyEngine`. Initial `work` branch was clean at
`c4550ecbd89bbf84363537e7bdf763c2177a998f`, an ancestor of the requested branch,
with no local-only commits. The initial fetch refspec selected only `main`; an
explicit fetch found the requested development branch at
`45de49c657f06c4301cc065c25cedf8066f763f6`. Switched the existing checkout to
`codex/r285-integration-20261114`, preserving the older branch. A final pre-commit
fetch found no newer target-branch work. `gh auth status` verified existing GitHub
authentication without requesting credentials. No worktree/reset/history rewrite.

Completed flow: authorized context → saved request → synthetic draft → private
approve/reject → current authorized reopen after service/connection restart.

- Strict version-1 provider, request, context, proposal and Activity envelopes.
- Reuse existing authorized public character projections, then whitelist scalar
  OOC reference fields. Player sees its own references; configured GM administrator
  sees public roster references; the current Handler sees roster callsigns only.
  Owner notes/setup secrets, fictional knowledge, raw state/events and transcripts
  are excluded. Sources retain character/owner/revision/field provenance.
- Deterministic, quoted extractive summaries with exact source/output validation.
  No AI SDK, credentials, network provider, freeform narration or paid call.
- Private immutable request/draft/review history in the existing authoritative
  campaign store, additive migration `0021`; no live migration. No new database.
- Existing command inbox and transaction boundaries: current authorization before
  replay, stable keys, expected campaign/proposal revisions, source freshness at
  generation/approval, rollback, sanitized terminal provider failures and pause.
  Stale/paused drafts may be rejected with current revision preconditions.
- Approval is a review record. Every result explicitly blocks application; no
  mechanical/canonical state, player choice, consent, Bond, activation, dice,
  resource, Discord delivery or outbox effect follows.

The [Activity handoff](../integrations/ai_assistance/INTEGRATION_HANDOFF.md)
defines logical operations and exact Python models. Proposed HTTP paths remain
unregistered. Framework, repository, backend, authentication and client ownership
must come from the Activity task before implementing its direct connection.

## Actual local verification

Runtime/test/CI-selection source snapshot SHA-256:
`7f60c01cb71a0a8979bf3523a2f6cd897b516c8c745668b122b75b88e313c9cd`.
The ignored `var/p2-source-snapshot.json` records each file hash. Reproduction:
make a mapping of SHA-256 hashes for `.github/ci-tests.txt`, migration `0021`, all
five `src/girlframe/ai/*.py` files, `database/{p2_schema,tables}.py`,
`services/ai_assistance.py`, and `tests/{test_ai_assistance,test_ai_context,test_database}.py`;
hash the UTF-8 JSON mapping with sorted keys and separators `(',', ':')`.
Reports/docs are excluded to avoid a self-referential digest. No runtime/test
source changed after this passing run. The publishing commit identifies the
complete source/docs checkpoint; remote CI is separate evidence.

`bash tools/install.sh` passed using the existing pinned lockfile. No lockfile or
dependency change.

```text
.venv/bin/pytest -q tests/test_ai_context.py tests/test_ai_assistance.py tests/test_database.py tests/test_character_transfer.py tests/test_onboarding.py::test_join_and_draft_replay_restart_and_stale_forms --junitxml=var/p2-assistance.xml
21 passed in 3.61s; zero failures/errors/skips; focused, not full regression.
```

Evidence covers both review outcomes; restart/readback and same-key replay;
privacy canaries and exact grounding; foreign owner/guild/campaign denial;
Handler replacement and membership revocation; campaign/proposal/source staleness;
rollback after staged audit/history; immutable records; safe outage/invalid output;
pause and explicit rejection; fresh migrations, schema parity and refused
destructive downgrade; affected existing file-transfer/onboarding workflows.
The first two attempts found new test-fixture mistakes (pause invocation, then a
reused generation command key), corrected before the passing run above. No
production code or existing assertion was weakened to obtain that pass.

Changed-file checks, including shared modules, migration and all changed tests:

```text
.venv/bin/ruff check src/girlframe/ai src/girlframe/services/ai_assistance.py src/girlframe/database/p2_schema.py src/girlframe/database/tables.py migrations/versions/0021_ai_assistance.py tests/test_ai_context.py tests/test_ai_assistance.py tests/test_database.py
All checks passed.
.venv/bin/ruff format --check <same paths>
12 files already formatted.
.venv/bin/mypy src/girlframe/ai src/girlframe/services/ai_assistance.py src/girlframe/database/p2_schema.py src/girlframe/database/tables.py
Success: no issues found in 8 source files.
```

`tools/check_rules_registry.py` passed, retaining RULES_SUBSET and existing review
counts. Original `verification/verify_handoff.py` passed: 34 required files,
86 planned cases, four schemas/four synthetic fixtures; planning evidence only.
`tools/check_repository.py` passed including this report: 2,069 publishable files,
40 manifest entries, zero findings. `git diff --check` passed. CLI help and health
passed; health used explicit disposable `/tmp/harpyengine-p2-offline-health.db`,
reported `discord_connected: false` and made no live connection. A bounded
technical integration review found no concrete defect in its declared integrity
scope; this is not independent rules certification.

The CI focused selection retains existing checks and adds both P2 test files and
database migration checks. No full regression was run for this bounded increment.
No Activity authentication, browser integration or human acceptance was tested.

## Remaining boundaries and next action

The actual Activity repository/backend/session handoff is the remaining dependency
for a direct connection. This does not block the delivered neutral contracts.
Fictional chronology/observed-knowledge adapters, freeform narration, real models,
external-data permission, spending limits and mechanical application remain
unsupported. The immediate synthetic provider runs inside the SQLite writer
transaction; a slow real provider requires a separately reviewed worker boundary.
P1 human acceptance, broader rules coverage and scoped production security remain
open. No bot restart, deployment, live state migration, environment publication,
passive ingestion or private recovered-engine mutation occurred.

Next: reconcile the Activity task's concrete backend/authentication handoff with
the v1 logical contract, then implement and test its private server adapter.
