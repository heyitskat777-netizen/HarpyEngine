# M2 acceptance — first character-creation step

**Status: first starting-choice step implemented and offline verified; M2 incomplete.**
**Date:** 2026-11-03 UTC. **Branch:** `codex/m2-character-builder`.
**Base:** tested M1 commit `76653db6872e6ff4a146b18541ec8d27fc5578bf`.

The owner authorized continuation after M1 smoke and explicitly chose official
JANUS rules with JANUS-B as the server label. This delivery implements
`docs/work_orders/M2A_STARTING_CHOICES.md`, within the larger character-builder
work order. It does not implement the original M2 Play wizard or activate PCs.

## Implemented behavior

`/character build` opens an owner-only ephemeral form for an existing saved draft.
Ten Girl and nine Frame catalogues provide source-backed starting Identities and
Asset options. JANUS-B resolves to JANUS mechanics while preserving its label.
The player chooses up to two distinct Assets of each family, describes them,
and supplies Frame name and appearances. Partial saves are supported; completing
these fields does not activate the character. Mockingbird's Void choice is tied
to a selected Girl Asset; Wyvern's Enormous is additional; Bonded Girl Assets wait
for Pair authorization. Missing requirements remain explicit.

Saved progress is append-only private SQLite data with command idempotency,
current-character and creation revision checks, guild/member/owner authorization,
and minimal private audit metadata. Descriptions never enter generic audit bodies,
public exports or sheets. The existing `/sheet` remains the M1 profile; reopen
`/character build` to view/edit creation details. Newer unsaved edits remain
explicitly unsaved if made while an earlier submission is committing. Changed
playbooks invalidate incompatible current choices without deleting saved history.

Migration 0004 adds one table and its immutability triggers. Full database backup
includes this history. Existing projection rebuild does not reconstruct creation
history from generic events; retain the database/backup as its authority. Private
creation records add to the existing retention/erasure policy work before wider use.

## Executed validation

| Command or check | Observed result |
|---|---|
| `bash tools/install.sh` | Locked installation succeeded; 36 packages resolved |
| `.venv/bin/ruff check .` | All checks passed |
| `.venv/bin/ruff format --check .` | 85 files already formatted |
| `.venv/bin/mypy` | No issues in 46 source files |
| `.venv/bin/pytest -q --junitxml=var/m2-starting-choices-pytest.xml` | 163 passed in 3.75 seconds; no skips |
| Handoff `verification/verify_handoff.py` | 34 required files, 86 historical planned cases, 4 schemas, 4 synthetic fixtures; PASS |
| `python tools/check_repository.py` | Zero findings; all 40 original manifest entries intact |
| `git diff --check` | PASS |
| Offline bot `start --config ... --check` | Policy/status fixture valid, 11 top-level command groups |
| Local database backup, `alembic upgrade head`, `alembic check` | Backup succeeded, schema 0004, no new upgrade operations |
| Compare private pre-migration backup to upgraded database | All 14 pre-existing application table contents unchanged; new creation table empty |
| Database integrity / foreign keys | PASS |

The new 26 test cases cover every catalogue branch, invalid options, Pair authority,
Void selection, private audit nonleakage, idempotency, concurrent/stale saves,
playbook changes, two-campaign isolation, immutable history, restart reads, actual
backup restoration, revocation (including replay), rollback after an inserted event,
native controls, owner checks, stale modals and successful private save callbacks.
The full suite retains all 137 prior tests. Fixtures are synthetic and outbound
network stays blocked. Managed-shell escalation was used for asyncio thread wakeups.
Tests do not constitute independent official-rules review.

During implementation lint caught fixture import placement and a missing generic
annotation; mypy caught the SDK Modal/View error-handler signature mismatch. Both
were corrected. The targeted builder suite passed 26 tests, followed by the full
163-test run above. No unresolved automated failure is known.

## Live evidence and remaining gates

No bot process was running in the current session before deployment. After backup
and migration, `tools/run_discord_dev.sh` reached Gateway READY. Authenticated
Discord REST readback confirms 11 guild command groups, character children
`create`, `sync`, `build`, and zero global commands. This verifies startup and
registration, not human interaction acceptance. The process remains temporary
session hosting. Environment configuration was neither changed nor published.

Human save/reopen smoke was requested for Mockingbird + JANUS-B. The owner replied
“I’ll test later” and requested continued development; it is **deferred by the owner**. No successful human builder interaction is claimed.
START-01 through START-04 have offline evidence; START-05 has offline migration,
actual preserved-database migration and registry evidence, with human smoke pending.
See `docs/acceptance/m2_starting_choices.json`.

BUILDER-01 through BUILDER-04 remain **NOT_RUN** for complete official creation.
Bonds/Pair consent, Handler Status, special playbook tracks and choices, starting
Heat verification, playable activation, independent rules review and official
Plays remain unfinished. The detailed source map and gaps are recorded in
`docs/RULE_COVERAGE_REPORT.md`. There is no AI, private-engine mutation, v1.3.11
integration, production-hosting claim or complete-rule certification in this change.

Only bot source, short choice labels/page references, migration, synthetic tests
and sanitized documentation are publishable. Official PDFs, extracted source text,
private engine packages, real character data, policy, database, backup and token
remain outside Git. Original handoff files are unchanged. GitHub CI evidence is
available on the branch's commits, separately from the local/live results above.

## M2B continuation — owner-authored playbook details

The owner requested continued development while deferring live smoke. This adds
Vatgrown's DNA-basis field and Prince's three native fanbase selectors: two
demographics, two demanded qualities, and two rejected qualities. The printed
custom spaces are supported with private text fields. Applicability, distinctness
and contradictory choices are checked before saving. Demographics are kept as
additional Identities; the Girl's four starting Identities are preserved. These are
draft choices, with no automatic Tags, Bonds, Heat changes or Play effects.

The source comparison was extended to rulebook PDF 48 and 61–62 and official sheet
18. See the coverage report and `M2B_PLAYBOOK_DETAILS.md`. The new optional fields
read old M2A JSON without rewriting stored history. No migration was added.

Targeted builder tests: **28 passed in 1.11 seconds**. These add legacy JSON, branch
applicability, custom choices, conflicting choices, native menu/modal interaction,
private restart reads, export nonleakage and owner denial. The first source commit
`88a235f` passed GitHub CI run 41602967309. The next full run and live restart are
recorded below; human M2A and M2B smoke remain unverified.

Final M2B regression: `.venv/bin/pytest -q --junitxml=var/m2-playbook-details-pytest.xml`
reported **165 passed in 3.85 seconds**. Lint, format (88 files), mypy (48 source
files), repository checks and schema drift check passed. No new migration operations
were detected. A fresh private backup was taken before deployment. No prior bot
process remained when deployment checked; development-session hosting is temporary.
Conflicting fanbase selections retain the existing form and unsaved choices while
showing the error. The fake interaction test verifies that behavior.

## M2C continuation — mutual starting-Bond setup

Implemented `docs/work_orders/M2C_BOND_PROPOSALS.md`: `/character bond member`
uses Discord's member picker and a native playbook-prompt selector, optional shared
context, review and explicit confirmation. `/character bonds [before]` privately
lists up to twenty participant proposals and opens accept/decline/withdraw controls.
The recipient must accept; either participant may withdraw an accepted setup
agreement. A source can cancel a pending proposal. No public/DM notification is
sent; saved proposals resume through the slash command after restart.

Nine Girl branches are supported: eight Personal and Bonded's Intense Pair. The
Newgirl source review found the additional Handler-assignment restriction at book
PDF 42 / printed 40; player-selected Mentor proposals are blocked with
UNSUPPORTED_RULE until that authority workflow exists. AM's review tells the
counterpart that the Girl is Jailbroken. Prompt labels are short paraphrases with
source anchors in the coverage report, not copied source passages.

Migration 0005 adds private immutable proposal revisions. Mutations require
campaign/guild/member/party authority, stable IDs, current profile/proposal revisions
and command idempotency, with minimal audit metadata committed atomically. Both
profiles and memberships must be current at acceptance. A change to either profile
revision or inactive membership marks the saved proposal/agreement stale. Source
outgoing duplicates and duplicate live proposals between the same pair are blocked.
Shared context is visible to both parties and private backup operators, never to a
third-party administrator through bot commands, generic event payloads, public
sheets or exports. History remains sensitive and subject to the outstanding wider
retention-policy work.

Executed checks:

- `.venv/bin/pytest -q --junitxml=var/m2-bond-proposals-pytest.xml`: **181 passed in
  6.16 seconds**, no skips. The new 16 cases cover all ten branches (including the
  blocked Mentor branch), two-party authority, state transitions, withdrawal,
  revoked membership on replay, duplicate/hash conflict, stale revisions, private
  data nonleakage, immutable history, campaign isolation, concurrent decisions,
  rollback, actual backup restoration, native review/acceptance and pagination.
- Ruff lint and format: PASS, 94 files formatted. Mypy: PASS, 51 source files.
- Original planning verifier: PASS, 34 required files, 86 historical cases,
  four schemas and four synthetic fixtures. All 40 handoff manifest entries intact.
- Repository check: zero findings. `git diff --check`: PASS.
- Private backup before upgrade: succeeded. Schema now 0005; `alembic check`
  detected no new operations. All 15 pre-existing application tables' contents
  matched the backup exactly; new proposal table empty. Integrity/foreign keys PASS.

Intermediate test failures were synthetic assertion mistakes: Markdown-escaped
canary comparison and a nonexistent test helper method. Both were corrected before
the final full run. The Newgirl authority restriction was corrected during source
review, before deployment. No unresolved automated failure is known.

These records are draft setup agreements only. They do not activate playable
characters, apply Bond mechanics, determine NPC Bonds, assign Mentors/Status,
complete Pair Asset selection, or imply fictional intimacy/actions. The full
creation validator must reconcile incoming/outgoing starting relationships before
activation. Independent rules review, BUILDER-01 through BUILDER-04 and original
M2 Play acceptance remain outstanding. Two-account human Bond smoke is NOT_RUN;
the owner previously deferred builder smoke and requested continued development.

No bot process remained at this deployment check, consistent with temporary
session hosting. Gateway/registry results are separate from offline tests. The
public branch contains sanitized source and synthetic evidence only; private PDFs,
engine, campaign data, policy, backups and credentials remain outside Git. No
environment configuration change or publication was attempted.

Live M2C startup reached Gateway READY. Authenticated Discord REST readback confirms
11 guild command groups, character children `create`, `sync`, `build`, `bond`,
`bonds`, and zero global commands. This confirms startup/registration only; human
Bond acceptance, decline and withdrawal remain unverified live.
