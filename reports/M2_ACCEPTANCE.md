# M2 acceptance — pilot implementation ready for owner review

## Authorized live M2 deployment — 2026-11-04 UTC

The owner explicitly instructed: “Yes, begin migration and bot restart.” The earlier
automatic approval block is resolved by that authorization. The deployment below
succeeded; implementation evidence and the earlier blocked attempt are retained
in the next section as history.

- Source: frozen tested `f97dd2ce0b69df726e8ef8ca540b33edec82e72c`, matching the
  reviewed candidate and current source SHA256 hashes. The source CI run passed:
  https://github.com/heyitskat777-netizen/HarpyEngine/actions/runs/41749655289.
- Read-only authenticated application/guild preflight passed before interruption.
- The single incumbent bot was gracefully stopped. New private WAL-consistent
  database and policy backups were created with mode 0600, outside Git.
- Live `alembic upgrade head` applied **0010 → 0011**. `alembic check` reported
  **No new upgrade operations detected.** All **21 existing application tables**
  exactly matched the pre-migration backup. Ten empty M2 tables were added.
- SQLite integrity: **ok**; foreign-key errors: **0**.
- Live policy now records the owner's Intense Tag modifier ruling as **2** and
  preserves all other prior settings. `m2_approval` remains **null**.
- Frozen-source offline startup check passed: `m2_review_gated`, 13 guild groups.
  Actual startup reached **HarpyEngine ready: commands registered in the configured
  test guild.** Exactly **one bot process** remains running.
- Authenticated Discord REST confirms **13 guild command groups, zero global
  commands**, including `play`, `choice`, character activation/state/follow-through/
  recovery, and campaign scene/order/recovery commands.
- Post-start data readback: **0 active M2 characters, 0 M2 actions, 0 M2 locks**.
  Startup and migration created no fictional effects or changed channel permissions.

No application source changed during this deployment; the established **433-test**
offline and CI evidence remains applicable. These checks establish startup,
registration and preservation, not human slash-command/mobile acceptance or
independent rules certification. Gameplay remains gated pending release review.
The environment draft was not changed or published; M3/AI work has not started.
Bot hosting remains temporary to the running session. Private deployment evidence
and backups are under ignored `var/`; no credentials, campaign data or PDFs are
included in the public documentation update.

## Earlier implementation and blocked-deployment evidence (retained)

## Current M2K evidence — 2026-11-04 UTC

**Implementation complete for the documented pilot subset; STOP for owner review.**
Independent certification and live human/mobile acceptance remain **NOT_RUN**.
The owner deferred play-testing to this end-of-M2 review. No M3/AI work started.
Current source follows tested M2J baseline `491f164` on `codex/m2-character-builder`.
Earlier sections below are retained historical evidence, not current deployment claims.

Implemented canonical activation/public visibility, immutable private state history,
Heat/Identities/Tags/Bonds/Status, five rolled Plays, diceless orders and the selected
Handler briefing, durable owned responses, future follow-through, nested escape
Plays, scene locking, recovery, projection rebuild and filtered public export.
Exact scope, source anchors, gates and human checklist are in
`docs/M2_REVIEW_HANDOFF.md`. The executable source registry links each Play to tests;
`docs/acceptance/m2_gameplay.json` maps M2-001..015 and additive LOCK/BUILDER cases.
The owner's Intense ±2 ruling is documented and in the private candidate policy;
it has not been applied to the running policy. Release approval remains absent.

| Executed check | Observed result |
|---|---|
| `bash tools/install.sh` | Locked install: resolved 36 packages, checked 35 |
| `.venv/bin/ruff check .` | All checks passed |
| `.venv/bin/ruff format --check .` | 158 files already formatted |
| `.venv/bin/mypy` | No issues in 86 source files |
| `.venv/bin/pytest -q --junitxml=var/m2k-pytest.xml` | **433 passed in 33.06s**, no failures/skips |
| Dedicated M2 suite | **129 passed in 14.37s** before final full run |
| Fresh disposable migration to head / `alembic check` | Schema 0011; no new upgrade operations |
| Offline copy of real DB, migrate 0010 → 0011 / check | All **21** original application tables exactly preserved; ten new empty M2 tables |
| Offline candidate integrity / foreign keys | `ok`; zero FK errors |
| CLI `--help`, `health`, `start --config ... --check` | Passed; source registers 13 guild-scoped groups; health remains M0 foundation evidence |
| Handoff verifier | 34 required files, 86 historical cases, four schemas/four synthetic fixtures; PASS |
| Publishable-file/manifest check | 238 publishable files, all 40 original manifest entries intact, zero findings |
| `git diff --check` | Passed |

Tests retain all 304 baseline cases and add 129 M2 cases, using synthetic records,
fake Discord and injected test dice. They cover all ten Girl and nine official
Frame activation branches plus JANUS-B, exact Play tiers/counts, ownership, public
projection, forced Heat, post-roll Tags, duplicate/concurrent actions, low Disobey,
all high Flirt branches, nested response Plays, mutual follow-through, permissions,
OOC pause, transaction rollback, restart/backup/rebuild and native selector/modal
controls. Production dice remain OS-backed. Source exceptions and future rules
outside the subset remain unsupported; these tests are not independent certification.

During development, full regression caught an incorrect `.scalars()` projection in
the revised public export. It was corrected to row iteration; the final 433-test
run passed. Fixture import/label issues, formatting and type errors were also fixed.
No unresolved automated failure is known. Human client behavior remains untested.

### Deployment status and approval block

A live restart/migration/policy update was attempted through the supported command
approval flow. **Automatic approval review rejected it** because it judged the
current authorization to cover M2 implementation and review, not this disruptive
live deployment. The rejected command did not execute. No process was stopped and
no live database/policy was changed. The remaining deployment requires owner approval.

A safer offline candidate was then prepared under ignored private `var/`: frozen
source with matching SHA256 hashes, a WAL-consistent backup, a separately migrated
copy, and a separate candidate policy with the approved Intense ruling. These
private artifacts are excluded from Git. Live DB stays schema **0010**; read-only
process verification confirms exactly **one incumbent M2J bot**. Discord REST still
reports **11 guild command groups, zero global commands**. Live M2 approval is absent.
No new M2 command registration, live permission mutation, activation, mechanical
roll or human smoke is claimed. The environment draft was not changed or published.

Review the concrete implementation and approve a controlled restart/migration when
ready. The bot remains on its previous working frozen build in this temporary
session. New M2 gameplay remains separately gated until independent release review.

---

## Historical M2A evidence (retained)


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

## M2D continuation — Handler authority and NPC setup

Implemented `docs/work_orders/M2D_HANDLER_NPC_SETUP.md` after owner authorization.
Configured administrators can preview/confirm Handler appointment or revocation
with `/campaign handler [member]`. The appointee must be an active joined member;
no appointment happens automatically. Appointments grant application setup authority,
not Discord permissions or access to private sheets/notes. Changing the Handler
clears current setup with a visible warning, retaining immutable history. Handler
accounts are outside Pilot ranking and starting player-Bond selection, even if an
account retains a test Pilot draft; affected proposals become stale.

The Handler nominates a Newgirl Mentor with `/campaign mentor newgirl member`.
A nomination unlocks Newgirl's existing private proposal only for that Mentor;
Newgirl confirms and the Mentor accepts. Nomination changes get a fresh token,
including reassignment to the same person, so old consent cannot be reused. Profile
changes, revoked membership and lost Handler authority block stale operations.
Mentor-chosen callsign and effective higher-Status behavior remain pending; no
automatic callsign or nickname change occurs.

`/campaign status_setup` selects all active Pilot profiles in order, reviews and
confirms the entire roster. First is Ace, last Dog, others Wings. Princess must
lead; multiple Princesses and fewer than two Pilots stop with UNSUPPORTED_RULE
rather than inventing an endpoint rule. The selector supports 2–25 Pilots. Reviewed
submission is captured before acknowledgement so a later UI edit cannot alter it.
Roster/profile changes mark stored order stale. No mission rewards, punishments,
orders or in-play rank shifts run. `/campaign setup` shows saved setup/staleness;
Mentor nominations are visible only to the Handler and the affected participants.

The creation wizard's NPC Bonds button supplies four sourced role options for
each Girl. Select 1–2, exactly 2 for Oldgen. Optional names and written feelings
stay in the owner's private creation history, never Handler views, public sheets,
exports or ledger payloads. Partial saves are supported; the wizard reports missing
required counts. The rules permit unwritten feelings. These descriptions neither
assign an unsupported starting NPC Bond depth nor merge NPCs into world canon.

Validation executed:

- Final `.venv/bin/pytest -q --junitxml=var/m2-handler-npc-pytest.xml`: **199 passed
  in 6.67 seconds**, no skips. New tests cover ten NPC branches, counts/duplicates,
  old JSON, private NPC modal/save, stale forms, explicit admin/Handler separation,
  appointment/revocation and revoked replay, complete/unique ranking, Princess,
  stale profiles, Mentor nomination plus mutual proposal/acceptance, fresh consent
  tokens, private view filtering, rollback, concurrent saves, immutable history,
  actual backup restoration, two-campaign isolation, native confirmation and late
  UI edits, and Handler-account exclusion from Pilot Bonds.
- A separate synthetic migration test populated schema 0005 with an existing
  private Bond proposal, upgraded it to 0006, and verified every original column
  value unchanged with nullable nomination provenance. Foreign keys and schema
  comparison passed. Existing tests also exercise fresh upgrade/downgrade.
- Ruff lint/format: PASS (102 files). Mypy: PASS (56 source files). Original handoff
  verifier: PASS (34 required files, 86 historical cases, four schemas/four synthetic
  fixtures); all 40 manifest entries intact. Repository check: zero findings.
  `git diff --check`: PASS.
- Before live migration, one prior test-bot process was signaled to stop. Private
  backup succeeded. Upgrade to 0006 and schema comparison passed. All original
  column values in all 16 pre-existing application tables matched the backup;
  new setup history was empty and old proposal nomination tokens NULL. Integrity
  and foreign keys passed. No Handler appointment was created by deployment.

An early fixture assertion incorrectly expected Bonded's entire creation to be
complete after NPC choices; it was corrected to check only NPC completeness while
leaving Pair-owned Assets pending. Static checks caught long SQL/string lines and
an unused test variable; all were corrected. The final suite above passed.

This is starting setup only. Pair Asset selection, remaining special Frame state,
Mentor callsign/effective Status, Cadre discussion, starting resources, playable
activation, original M2 Plays and independent full-rule review remain outstanding.
BUILDER-01 through BUILDER-04 remain NOT_RUN for complete official creation. Human
smoke for these new workflows is NOT_RUN; existing owner-deferred builder/Bond
smoke remains distinct from automated evidence. No environment configuration was
changed or published. Private sources, data, backups, policy and credentials stay
outside Git; canonical private engine files remain untouched.

M2D live startup reached Gateway READY. Authenticated Discord REST readback shows
11 guild command groups, campaign children `join`, `create`, `status`, `handler`,
`mentor`, `status_setup`, `setup`, and zero global commands. This is startup and
registration evidence, not human acceptance of authority, ranking or NPC forms.

## M2E continuation — Pair-owned Assets and Frame baselines

Implemented `docs/work_orders/M2E_PAIR_FRAME_SETUP.md` after the owner's continued
M2 authorization. The accepted Pair uses `/character pair_assets member` or
**Choose Pair Assets** on an accepted Bonded proposal. A native selector requires
two distinct sourced Girl Asset names and explicit confirmation. The Bonded owner
sees those names in a disabled selector, supplies descriptions in their private
builder and explicitly saves. Pair selection does not read or write the owner's
private creation body; Bond profile checks now select only public profile columns.

Migration 0007 adds immutable allocation revisions tied by FK to the authorizing
accepted Bond revision. Every save checks current membership, Pair identity and
fresh agreement inside the transaction, including inbox replay. Owner saves carry
an allocation token and record it with their descriptions. Changed choices or
withdrawn/stale agreements block old forms; incompatible descriptions disappear
from the current view without deleting immutable history. Matching descriptions
can be retained for owner review and explicit saving against the new allocation.
The Pair can never choose Frame Assets or write descriptions for the Bonded owner.

Saved creation progress also records a schema-versioned Frame baseline with source
PDF anchors. JANUS/JANUS-B includes a distinct unnamed Harpy Core with its four
prescribed starting Tags. This is a nested draft record, not a fully implemented
targetable game entity. DoctorDoctor records eight-box capacity; CONSUME records
Quiet/Gnawing/Ravenous; Wyvern records fixed Enormous; Red Queen records five AM roles
and default four-self/one-other split. Starting starvation/marked-box values and
actual external AM role/recipient selection/agreement remain explicit pending
requirements. No Heat, Core naming/choices, Plays, rewards or consequences run.
The Frame setup button retains the creation form and unsaved edits. Legacy JSON
remains readable; deriving facts on reopen does not write until Save progress.

Executed validation:

- Final `.venv/bin/pytest -q --junitxml=var/m2-pair-frame-pytest.xml`: **213 passed in
  9.75 seconds**, no skips. The 14 new cases exercise every Frame branch/JANUS-B,
  serialization and rejected baseline/Core forgery, illegal/duplicate names, Pair
  vs owner/administrator authority, owner descriptions and provenance, changed
  selection/withdrawal, revoked replay, privacy, concurrent choices, transaction
  rollback, immutable history, actual backup restoration, campaign isolation,
  profile changes, native Pair controls and retained Frame-facts form.
- Ruff lint/format: PASS (109 files). Mypy: PASS (60 source files). Original
  planning verifier: PASS (34 required files, 86 historical cases, four schemas and
  four synthetic fixtures). All 40 handoff manifest entries unchanged. Repository
  check: zero findings. `git diff --check`: PASS.
- One prior test-bot process was signaled to stop. Private backup succeeded before
  upgrade. Schema 0007 and `alembic check` passed. Original values in all 17 prior
  application tables matched the backup exactly. Integrity and foreign keys PASS;
  the new allocation table was empty. Deployment made no Pair selection.

Targeted existing workflow checks passed 64 tests; the new Pair/Frame module passed
14 tests before full regressions. Explicit provenance was added and revalidated in
the final run above. Static checks caught one long response string; corrected. No
unresolved automated failure is known.

Human Pair/Frame smoke remains NOT_RUN, distinct from offline evidence and command
registration. The owner previously deferred builder testing and requested continued
work. Remaining M2 work includes actual Court assignment, starting counters, Mentor
callsign/effective Status, Cadre discussion, complete sheet validation and activation,
original Play workflows and independent rules review. BUILDER-01 through BUILDER-04
remain NOT_RUN for complete official creation. Private source PDFs/engine, campaign
state, policy, backups and credentials remain outside Git; canonical engine files
are untouched. No environment configuration change or publication was attempted.

M2E live startup reached Gateway READY. Authenticated Discord REST readback confirms
11 guild command groups, character children `create`, `sync`, `build`, `bond`,
`bonds`, `pair_assets`, and zero global commands. Human two-player Pair selection
and description testing remains NOT_RUN; this readback verifies registration only.

## M2F continuation — Court and Mentor choices

Implemented `docs/work_orders/M2F_COURT_MENTOR_CHOICES.md` after owner continuation.
A Red Queen pilot uses `/character court member` to select one of the five AM roles
for another Girl and confirm a private request. The recipient accepts/declines via
`/character requests [before]`; either participant can withdraw accepted setup.
The accepted allocation contains exactly one AM on the recipient and the other
four on the source pilot, including when Queen is chosen externally. No Court
controller permission, AM marking, transfer, Decree or compulsory action is run.

The accepted Mentor uses `/character mentor_callsign member` to propose a name.
The Newgirl accepts or declines the private request. Authority requires current
Handler nomination and accepted Mentor Bond, with both profiles current. Changing
that nomination/relationship invalidates the request, including stale replay. The
name is intended for the final sheet at activation; public profile and Discord
nickname are unchanged now, avoiding implicit profile edits invalidating consent.

`/campaign effective_status member` compares the requester's setup Status against
one counterpart. It recognizes the current accepted Mentor exception in both
directions, active Handler priority and a fresh starting rank order. Stale or
unresolved comparisons return unknown; reciprocal Mentor authority is explicitly
unresolved. This read-only helper performs no orders, Punishments, Tag rules or
other in-play effects. Other Mentor duties require later Play/scene workflows.

Migration 0008 adds private immutable shared-request revisions. All commands use
campaign/guild/member/party authority, exact current source roles, profile and
request revisions, constraint tokens, idempotency and transactional checks. No
administrator override exposes shared values. Event/outcome payloads contain
minimal metadata; names/roles remain in private request records. Current accepted
choices appear in the owner's builder. Save progress records provenance tokens and
rejects a form if shared agreement changed. Requests survive restart and page in
batches of twenty using UUID cursors. No DM or public notification is sent.

Executed validation:

- Final `.venv/bin/pytest -q --junitxml=var/m2-court-mentor-pytest.xml`: **226 passed
  in 7.85 seconds**, no skips. The new 13 cases cover all five AM choices/four-one
  mapping, legal role/recipient/source rules, Mentor authority, private acceptance,
  decline/withdraw/revoked replay, nomination/profile staleness, provenance/forged
  tokens, effective Status, concurrency, rollback, immutable history, actual backup
  restoration, two-campaign isolation, pagination, native Court controls, callsign
  forms and recipient decisions. No public profile/nickname update is asserted.
- Before adding new tests, all 213 prior regressions passed; the first targeted
  shared-setup module run passed 11 cases, then additional native-name/pagination
  coverage was added. Static checks caught long UI strings and a Literal typing
  mismatch, corrected before final validation. No unresolved automated failure.
- Ruff lint/format: PASS (115 files). Mypy: PASS (63 source files). Handoff verifier:
  PASS (34 required files, 86 historical cases, four schemas/four synthetic fixtures).
  All 40 manifest entries intact; repository check zero findings. `git diff --check`
  passed. Private official source PDF pages 42 and 88–89 were rechecked directly.
- No prior bot process remained at this deployment check. Private backup succeeded
  before migration; schema is 0008 and schema comparison detected no changes.
  All original values in the 18 pre-existing application tables matched backup;
  integrity/foreign keys PASS, new request history empty. No setup choice was made
  by deployment. Development-session hosting remains temporary.

Human Court/callsign/Status smoke remains NOT_RUN, distinct from offline and
registration evidence. The owner deferred earlier live builder testing and asked
to continue. Remaining work includes starting counters/resources, Cadre discussion,
complete validation, activation/name application, further Mentor duties, original
M2 Play workflows and independent official-rules review. BUILDER-01 through
BUILDER-04 remain NOT_RUN for complete official creation. Only sanitized code and
synthetic evidence enter Git. Private PDFs/engine, data, policy, backups and tokens
remain outside Git. Canonical engine and environment configuration were not changed;
no environment publication was attempted.

M2F live startup reached Gateway READY. Authenticated Discord REST readback confirms
11 guild command groups, character commands `create`, `sync`, `build`, `bond`,
`bonds`, `pair_assets`, `court`, `mentor_callsign`, `requests`, and campaign commands
`join`, `create`, `status`, `handler`, `mentor`, `status_setup`, `setup`,
`effective_status`, with zero global commands. Source finalization hides the unrelated
callsign button from the Court form; the process was reloaded for that UI change.
Human multiplayer request/Status acceptance remains NOT_RUN.

## M2G — recommended overview inbox and guided review

The owner selected the recommendation: A overview inbox opening B detailed review,
superseding the earlier B-only choice. `/character requests` now opens five private
summaries per page. Pending / Needs you / Waiting / History, category filtering,
request dropdown, Previous / Next / Refresh / Close and Back require no typed IDs
or cursors. A selected source identity/revision is revalidated before review;
role-specific decision buttons are bound to their rendered request and generation.
A rapid click from an older panel cannot accept the next request.

The service projects all eligible starting Bond, Court and Mentor-callsign records
in one read transaction, including more than the earlier twenty-record limit.
Only the current participant sees shared context. Counts and paging operate over
the combined eligible set; stale pending outgoing requests require the sender's
review rather than appearing as ordinary waiting work. No administrator bypass
exposes private content. Existing services own decisions, expected revisions,
permissions and idempotency. No new mechanical effects or automatic assignments.

Derived tasks cover nominated Newgirl agreement, accepted Mentor callsign choice,
Red Queen external assignment, Pair-selected Asset names and owner-only Asset
descriptions. They open the existing authorized wizards; opening saves nothing.
Fresh downstream requests/accepted choices replace tasks rather than duplicating
them. A dedicated read-navigation budget permits paging without weakening metadata
mutation limits. The legacy `/character bonds` flow remains available.

Executed validation:

- `bash tools/install.sh`: resolved 36 packages, checked 35; pinned lock unchanged.
- `.venv/bin/pytest -q --junitxml=var/m2-request-inbox-pytest.xml`: **242 passed in
  12.12 seconds**, no skips. Sixteen inbox cases cover mixed sources and more than
  twenty records, categories/scopes, role actions, exact replay, membership/profile
  changes, two-campaign isolation, task deduplication, private Pair descriptions,
  native task routing/Back, stale and rapid clicks, reopening, five-item overview
  paging and version-bound overview-to-detail selection. Targeted inbox run:
  **16 passed in 3.23 seconds**. Existing service/storage regression evidence remains
  applicable; no schema or source-service mutation behavior changed.
- Ruff lint/format: PASS (126 files); mypy: PASS (66 source files).
  Planning verifier: PASS (34 required files, 86 historical cases, four schemas and
  four synthetic fixtures). Repository scanner: 203 publishable files, all 40
  original manifest entries intact, zero findings. `git diff --check`: PASS.
- Local health and startup `--check`: PASS; eleven guild command groups configured.
  `alembic check`: no new upgrade operations. No migration required (schema 0008).
- No existing development bot process remained. A new private database backup
  succeeded before startup. Updated bot reached Gateway READY. Authenticated REST
  readback confirms eleven guild command groups, zero global commands, all nine
  existing character subcommands and `/character requests` with no arguments and
  its new inbox description. No fake campaign request or gameplay action was
  created for deployment verification. Hosting remains a temporary session process.

Human multiplayer/native-client smoke is **NOT_RUN**, distinct from the automated
fake-adapter tests and real login/registration. Earlier owner-deferred creation
checks remain pending. See `docs/acceptance/m2_request_inbox.json`. The synthetic
browser mockup, SDK layout proof and rendered screenshots are retained under
`design/request-inbox/`; they are design references, not real campaign records.

The intended `/play` selectors and guided Confirm & Roll/result-choice flow are
recorded in `design/play-picker/README.md`. The owner additionally requested scene
chat freezing while a real Play is pending. `M2H_PLAY_CHANNEL_LOCK.md` specifies
permission preflight, durable acquisition before RNG/spend, required-response
controls, safe restoration, staff unlock and restart recovery. It explicitly
records administrator bypass and temporary-hosting limitations. That extension
is **SPECIFIED / NOT_IMPLEMENTED**; LOCK-01 through LOCK-12 are **NOT_RUN**. It
depends on an audited Play resolver and durable pending actions. Current setup
requests and raw dice do not lock chat. Bond elevation/change and other in-play
responses need their rule-specific adapters. No actual `/play`, permission lock,
AI, playable activation or engine writes are claimed.

Rollback is a code revert and process restart; saved requests remain in the existing
schema. No downgrade or database reset is necessary. Only sanitized source, tests,
docs and synthetic design artifacts enter the public repository. Official PDFs,
private engine, policy, campaign state, backups and credentials remain excluded.
The original handoff and environment configuration were preserved; no environment
publication was attempted.

## M2I — private creation validation and review-sheet snapshots

The owner authorized continuation as far as prerequisites allow. Implemented
`docs/work_orders/M2I_CREATION_REVIEW.md`: `/character review` combines saved choices,
source-backed starting access, accepted relationships, current Status and explicit
starting-resource rulings in an owner-only paged sheet. Validation covers every
Girl and Frame branch plus combined special cases. A review snapshot can be saved
while incomplete; it is always `draft_rules_unverified`, never a playable character.
Reviewing does not save unsaved builder edits, publish private descriptions or
create game events/effects. Snapshot saves append private revision history and
minimal metadata audit events, with consistent read snapshots, expected revisions,
dependency fingerprints and owner/membership checks. A stale/rapid control cannot
save an unreviewed replacement snapshot.

Newgirl can declare zero or one prior mission with each current Cadre counterpart
(including the appointed Handler) through native selectors, then attest that those
declarations were discussed in conversation. Edits clear the attestation. Roster or
profile changes require updated references. This step is available from the builder
and unified inbox; saving the completed declaration removes the derived task. No
conversation, counterpart response, consent or notification is fabricated.

Found and corrected a creation dead end: requiring all Pilots to originate their
starting Bond conflicts with mutual Bonds and the existing prohibition on reverse
duplicate proposals. A player may explicitly select and confirm an eligible accepted
incoming Personal Bond as the starting choice. Source-owned eligible proposals
remain the default for their owners. Exact depth and Newgirl/Bonded role checks
remain enforced. Obsolete explicit choices can be cleared. No automatic Intense-to-
Personal conversion is invented. Received Court roles now appear on recipients'
review sheets; withdrawal invalidates current review freshness without deleting
history. Source/recipient private creation bodies remain isolated.

The owner explicitly approved starting **Heat 0, CONSUME Quiet, DoctorDoctor 0
marked boxes**. Applied those as `owner_approved_campaign_ruling` in the existing
private local policy, preserving every other setting and backing up the original.
The public example leaves owner defaults null. Appointed Handler controls can
preview/confirm their own explicit ruling or unresolved override, with different
provenance; a Discord caller cannot forge owner approval. No synthetic Handler
command or user identity was created, and no actual character resource pool was
initialized. Regular mode has no optional starting Requisition; the short-game
variant remains unsupported and visibly blocks readiness.

Source audit: book PDF 7/10/13/14/40/42/60/65/71 and corresponding official sheets,
plus the existing source-linked playbook catalogues. Initial Heat/hunger values
were not inferred from absent text; the numeric values above are campaign rulings.
Details and remaining source gaps are in `docs/RULE_COVERAGE_REPORT.md` and the new
`docs/M2_RULES_REVIEW_PACKET.md`. Independent source/code review, final publication,
Newgirl profile/name application, NPC depth/initial marked-state verification,
transactional playable activation, game-service consumption and official Plays
remain pending. UI activation is disabled; the service also returns
`UNSUPPORTED_RULE` if called directly. BUILDER-01–04 and LOCK-01–12 remain NOT_RUN.

Executed validation:

- `bash tools/install.sh`: resolved 36 packages / checked 35, committed lock unchanged.
- Final `.venv/bin/pytest -q --junitxml=var/m2-creation-review-pytest.xml`:
  **283 passed in 13.80 seconds**, no skips. Forty-one new cases include all ten
  Girls, all nine Frames plus JANUS-B, combined Newgirl/Court/Prince and Pair/Prince/
  Wyvern branches, missing/unsupported choices, current-role and depth enforcement,
  stale source/roster/ruling dependencies, owner-only projections, explicit native
  confirmation, old clicks, long-text paging, unchanged mutation throttles,
  exact replay, immutable history, rollback, concurrency, actual private backup
  restoration, membership revocation and two-campaign isolation.
- Intermediate targeted review run: 30 passed in 4.29 seconds; review + prior inbox
  suite after mutual-choice/default-provenance additions: 51 passed in 7.73 seconds.
  Full run before additional cross-playbook cases: 278 passed in 18.43 seconds.
  Lint caught long strings/import ordering, and mypy caught literal/default type
  annotations; corrected before final checks. No unresolved automated failures.
- Final Ruff lint/format: PASS (135 files); mypy: PASS (71 source files).
  Planning verifier: PASS (34 required files, 86 historical cases, four schemas and
  four synthetic fixtures). Repository check: 213 publishable files, all 40 handoff
  manifest entries intact, zero findings. `git diff --check`: PASS.
- Stopped the single matching development bot gracefully. Private pre-migration
  database backup succeeded; additive migration **0009** applied. `alembic check`:
  no new upgrade operations. Read-only comparison against backup confirmed every
  value in all **19 pre-existing application tables unchanged**. Integrity/foreign
  keys PASS; new review history empty. No fake request or review record was created.
- Updated startup `--check` PASS; Gateway reached READY. Authenticated Discord REST
  readback confirms eleven guild command groups, zero global commands, all prior
  commands, new `/character review` and `/campaign creation_rules` with no arguments.
  Existing inbox and ordinary dice/safety flows remain registered. Local health PASS.
  Runtime is still temporary development-session hosting.

Native-client multiplayer review/history/Bond-selection/ruling smoke remains
**NOT_RUN**. Existing owner-deferred M2 live checks remain pending. Automated tests,
live login/registration and human acceptance are distinct. Acceptance mapping:
`docs/acceptance/m2_creation_review.json`. No real campaign content entered tests,
logs or public source; official PDFs, engine, policy and backups remain excluded.

Recovery: retain migrated schema and prefer a forward fix. Older code/policy parsers
may not understand newly saved draft/setup fields or owner-default configuration;
a blind code rollback after feature use is not a compatibility guarantee. Private
pre-migration data/policy backups are available. Restore only to a new offline path
for deliberate recovery; do not downgrade/delete a populated database. Original
handoff and canonical engine were preserved; no environment configuration was
published or repinned. This step does not claim production security, complete
creation certification, activation, AI, `/play` or scene-chat locking.

## M2J — mandatory playbook choices and coordinated authorship

The owner requested continued work while keeping the bot available. The next source
audit found mandatory creation choices outside the first playbook creation page:
Princess standards (book PDF 32 / printed 30), Oldgen maxims (46 / 44), Vatgrown
Investor desires (49 / 47), and CHANGELING's explicit starting Psych String note
(82 / 80). Added these requirements before allowing readiness to treat the relevant
branches as filled. The earlier source-version-1 review was not certification of
these missing requirements. Independent complete-source review remains pending.

`/character build` now includes **Girl setup** for Princess/Oldgen/Vatgrown. Owners
choose their own standard, two maxims, or one/two desires for each selected NPC
investor, with custom standard text where the source allows it. Save progress is
explicit. Changing selected NPC roles filters incompatible investor choices from
the current form and retains immutable saved history. No unprinted requirement
forces the three Princess standards to be distinct.

Bonded Girls and appointed Handlers author their own Princess standards; the
Handler authors its own Vatgrown investor desires. Derived inbox tasks open native
dropdowns and a private confirmed proposal. The character owner reviews the result
through the same source-unified inbox, with accept/decline/withdraw as authorized.
The owner cannot fill another chooser's role. Handler authors require membership
and explicit appointment, without requiring a fake Pilot profile. Authority binds
current profiles, relevant accepted Bond and the actual appointment event, rather
than a reusable Handler name. Reappointing the same account after revocation cannot
revive old consent. Unrelated rank/ruling changes do not rewrite author authority.
All parties have private history; other administrators have no private-data override.

New immutable coordination storage uses membership FK for authors and character FK
for owners. Writes use campaign identity, current authority/version, idempotency and
transactional audit. Old/stale accept replays revalidate authority; stale old chooser
buttons cannot send a newer selection. Duplicate current requests replace tasks
instead of duplicating them. No DM/public notification, order, punishment, consent
for fictional behavior or runtime Play is emitted by setup acceptance.

Review source version **2** adds the new requirements and private choices. Version
1 remains readable historical data and is not considered a fresh current snapshot.
CHANGELING records draft anchors for current accepted player Bonds and owner-local
NPC roles, without creating world NPCs or using Psych Strings. Casualty's nine
source body parts and Bonded's protected Paired Identity are visible as draft facts.
The owner additionally approved unmarked Identities/maxims, undamaged Assets/body
parts, Personal NPC Bonds, 0 Permissions, no acquired Requisitions and no extra Tags,
with printed exceptions preserved. These are `owner_initial_conditions` in trusted
private policy, not claimed printed defaults or initialized gameplay pools. Earlier
0 Heat / Quiet / 0 obsolescence rulings remain unchanged.

Executed validation:

- Locked install: resolved 36 / checked 35 packages, dependency lock unchanged.
- Initial existing creation/inbox/database targeted regression: **87 passed in
  7.18 seconds**. New coordination module initially **18 passed in 2.19 seconds**;
  then additional distinct-author/source-contract and stale-send cases were added.
- Final `.venv/bin/pytest -q --junitxml=var/m2-playbook-creation-pytest.xml`:
  **304 passed in 16.32 seconds**, no skips. Twenty-one new cases cover all chooser
  roles, Handler without Pilot profile, source choice models, profile/Bond/Handler
  replacement, revoked replay, duplication, decision states, private immutable
  history, rollback/concurrency, actual backup restoration, isolation, missing
  readiness, old review compatibility, owner progress, custom text, NPC edits,
  native inbox routing and version-bound explicit sending.
- The first full run had **302 passes / one failure**: a new test reused the fixture's
  prior interaction key for a different replacement request, correctly producing
  IDEMPOTENCY_CONFLICT. Corrected that synthetic key and added stale-send coverage
  before the final passing run. Static literal/string/import issues were corrected.
  No unresolved automated failure or skipped automated case.
- Ruff lint/format PASS (142 files); mypy PASS (75 source files). Shell startup syntax
  PASS. Planning verifier PASS (34 required files, 86 historical cases, four schemas/
  four synthetic fixtures); all 40 manifest entries intact. Repository scanner:
  221 publishable files, zero findings. `git diff --check` PASS.
- Verified one incumbent bot process during development and left it running through
  editing/testing. Created a private frozen source release; verified actual module
  resolution and offline startup from that source. Optional trusted
  `GIRLFRAME_RUNTIME_SOURCE` in the startup wrapper selects this tested copy without
  copying data/policy into source. Later checkout edits cannot change this process's
  package files. A prior source copy is retained privately for recovery reference.
- During the brief controlled cutover, stopped the incumbent gracefully, created a
  private database backup, then applied additive migration **0010**. Alembic schema
  comparison found no new upgrade operations. Every value in all **20 pre-existing
  application tables matched backup**. Integrity/foreign keys PASS; new coordination
  history empty. No real request, choice or snapshot was fabricated for deployment.
- Backed up private policy and applied the owner's explicit initial-state rulings,
  preserving all other settings. New runtime reached Discord Gateway READY. Follow-up
  confirms one bot process, frozen source hashes matching tested checkout and the
  approved configuration. Authenticated REST readback confirms eleven guild command
  groups, build/inbox/review present, zero global commands. Local health PASS.

Human native-client Princess/Oldgen/Vatgrown/CHANGELING smoke is **NOT_RUN**, distinct
from offline tests and live login/registration. Earlier owner-deferred M2 live checks
remain pending. Mapping: `docs/acceptance/m2_playbook_creation.json`. The source/code
review packet and coverage report include the new anchors and approved rulings.

Playable activation, final public-sheet publication, safe Newgirl name/profile
transition, gameplay-service consumption and original M2 official Plays remain
unfinished. Independent complete-source review is still required; no certification
or activation was enabled. Complete-builder and scene-lock cases remain NOT_RUN.
This is development-session hosting, not continuous hosting across machine shutdown.
The frozen source protects against edits, not host loss. No environment publication
or repinning was attempted. Private PDFs/engine, policy, campaign records, backups
and credentials remain outside Git; original handoff and canonical engine preserved.
Recovery favors a forward fix: older parsers may not accept new saved choice fields,
source-version-2 reviews or policy fields after feature use. Preserve schema/history;
restore backups only to deliberate new offline recovery paths, not by deleting data.
