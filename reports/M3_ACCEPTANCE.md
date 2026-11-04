# M3 acceptance — scoped, implementation not yet certified

Status: IN_PROGRESS / RULES_SUBSET. Date: 2026-11-04 UTC.

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


## M3 source/core foundation checkpoint — 2026-11-04 UTC

The owner authorized continuing until a genuine intervention point or M3 completion.
The source audit established the supplied 205-page book and 56-page sheets, added
`rules/registry.json` and its strict validation, and began pure core/economy/shared
Play/mission components. `docs/M3_SOURCE_AUDIT.md` details actual scope and gaps.
Ancillary playbooks are deferred/disabled by explicit owner instruction. The owner
also approved the reprogramming fallback, three 1-Permission Requisition prices,
and per-repair Handler quotes. The absent Ace reward policy is still awaiting input.
No assumption is made on that branch; no M3-complete claim is made.

Executed validation:

| Check | Actual result |
|---|---|
| `.venv/bin/ruff check .` | All checks passed |
| `.venv/bin/ruff format --check .` | 172 files already formatted |
| `.venv/bin/mypy` | No issues in 92 source files |
| `.venv/bin/pytest -q tests/rules` | **62 passed in 4.79s** |
| Full suite, `--junitxml=var/m3-foundation-pytest.xml` | **500 tests, zero failures/errors/skips**, JUnit time 38.521s |
| `python tools/check_rules_registry.py` | RULES_SUBSET; 473 inventory entries, 436 core required, 37 deferred; zero independent verification |
| Repository check before documentation update | 254 publishable files, 40 manifest entries intact, zero findings |
| `git diff --check` | Passed |

The initial extraction hit an image-block serialization error and a test used the
wrong registry file parent; both were corrected. A tier return type was narrowed
to its existing literal values for mypy, without changing M2 runtime behavior.

Full M3 regression cases remain NOT_RUN or IN_PROGRESS, not PASS. A choice contract
is not a complete mechanical resolver. Further branch audit, all playbook effects,
state/service/migration/UI integration, Strain resolution, world entities and
independent/human acceptance remain. No M3 schema or live policy changes occurred.

The environment restarted during the work. The uncommitted checkpoint and completed
500-test JUnit evidence survived; the temporary bot process did not. The previously
tested frozen presence build was restarted after hash/offline-check verification,
without loading the developing M3 source. Its live READY/presence output is checked
separately from the rules tests. No environment configuration was published.


## Transactional private mission checkpoint

The owner approved granting the current Ace its separate mission-end Permission
when absent. This is now recorded as a campaign ruling, not printed-rule certainty.
The source branch adds a scoped, digest-bound M3 approval and explicit trusted M3
rulings. Both default to absent; incomplete coverage cannot claim a core-complete
release. Synthetic test approvals are not independent certification or live approval.

Mission offers, individual responses, dispatch, explicit outcomes and rewards are
persisted with private immutable histories. Permission changes and required-work
records commit atomically through the existing canonical Pilot state. Failure and
Dog causes remain separate auditable records, including an absent Dog. Known
Princess/DoctorDoctor end reactions block the final reward snapshot; no generic
acknowledgment waives consequences. Their actual resolvers and the remaining
playbook trigger audit are unfinished.

Native private `/mission offer`, `/mission inbox` and `/mission show` controls and
the requests inbox use authenticated ownership and expected revisions. Opening a
menu never accepts an offer. Unauthorized members/admins cannot read objectives;
an absent Dog sees required work without the objective. Saved reads survive a
vacant Handler appointment while writes stay blocked. Mission projections rebuild
from immutable history; backup/restore preserves rewards and work. New source
registers 14 guild command groups; the live frozen source still has 13.

Validation executed:

| Check | Actual result |
|---|---|
| `bash tools/install.sh` | Locked environment checked: 36 resolved / 35 installed packages; no dependency change |
| `.venv/bin/ruff check .` | All checks passed |
| `.venv/bin/ruff format --check .` | 181 files already formatted |
| `.venv/bin/mypy` | No issues in 97 source files |
| Full offline suite, `--junitxml=var/m3-missions-pytest.xml` | **520 passed in 46.41s**, zero failures/errors/skips |
| Fresh migration/check/downgrade | Passed in the full synthetic suite; 34 application tables |
| Populated synthetic `0011` to `0012` migration | All rows of all 31 existing application tables unchanged; three new tables empty; Alembic no pending operations; integrity `ok`, zero FK errors |
| Registry check | RULES_SUBSET; 473 inventory entries, 436 core required, zero independently verified |
| Handoff verifier | 34 required files, 86 planned cases, four schemas and four synthetic fixtures; PASS for planning package only |
| Publishable-file/manifest check | 263 files, all 40 original manifest entries intact, zero findings |
| CLI help and local health; startup wrapper `bash -n` | Passed; no Discord connection made by these smoke checks |
| `git diff --check` | Passed |

The final suite adds 20 cases over the prior 500-test baseline: service, native UI,
migration preservation and Handler-vacancy regressions. Two initial migration-test
assertions used the wrong action-read API/shape; both were corrected before the
passing full run. No application failure remains from those test authoring errors.

Live readback found exactly one existing bot process, schema **0011**, database
integrity `ok` and zero FK errors. The frozen presence release, live policy and live
database were not replaced or migrated. These are local operational observations,
not human Discord acceptance of the M3 UI. Future M3 frozen releases must include
the matching source registry beside `src/`; the startup wrapper binds its snapshot.
No credentials, PDFs, private references, databases or environment configuration
were published.

M3 remains IN_PROGRESS / RULES_SUBSET. Punishment application awaits two genuine
owner interpretations (book PDF 17–18 / printed 15–16, and PDF 16–17): who selects
unspecified Identity/Asset details after the inflictor chooses the type, and whether
one actual Punishment can satisfy both failure and Dog causes. No assumption on
either has been committed. Full remaining mechanics, Strain/world rules, independent
source/code review, human acceptance and owner milestone sign-off are still required.


## Inflictor-owned discipline checkpoint

The owner resolved both pending Punishment questions: the inflictor selects all
unspecified details, with explicit printed choice ownership taking precedence;
one actual Punishment satisfies both mission-failure and Dog causes for the same
Girl in the same mission. Registry and trusted policy models record those exact
rulings. Both source causes retain distinct immutable records and reference the
same application event. The rulings have not been applied to the live policy.

Pure reducers implement Sedation, Beating, Reduced Socialization, Quality Time,
Demotion, Stimulant Injection, Correctional Programming, Frame Disassembly,
Compliance Surgery and Libido Inhibitor. Passing Responsibility transfers all
pending failure/Dog causes to a chosen active Pilot without applying a consequence.
Handler/Pilot authority and explicit printed protected Identity rules are checked.
Personal Bonds erase when weakened; strengthening beyond Intense grants two Heat
to both characters, including tracked Handler Heat. Off-duty Sedation locks survive
pure recovery attempts, while this service handles pre-Off-Duty mission discipline.

The transactional service adds exact-proposal Moderate consultation: a delegated
Girl proposes legal choices, the current Handler reviews and explicitly answers,
then the inflictor applies precisely approved choices. Approval binds game revision,
work revisions and Handler. Changed state/choices invalidate it. A different legal
Minor Punishment or delegation supersedes an unneeded consultation without waiving
the actual Punishment. Duplicate/concurrent submissions cannot apply twice, and
failed writes roll back effects, history and all cause records together.

`/mission discipline` and the existing requests inbox open native private selectors,
modals and confirmations. The subject cannot choose inflictor-owned details. The
inflictor receives necessary Identity/Asset/Tag labels, not private descriptions,
notes, NPC drafts, review snapshots or the mission objective. Severe/unimplemented
types are unavailable. Explicit Paired Identity Heat sharing remains the affected
owner's choice; its allocation is durable/idempotent and cannot be chosen by the
inflictor. Immediate follow-ups block new Plays and false mission completion.

Executed checks:

| Check | Actual result |
|---|---|
| Locked installer | 36 packages resolved, 35 installed packages checked; no dependency change |
| Ruff lint / format | All checks passed; 187 files already formatted |
| Mypy | No issues in 100 source files |
| Focused initial pure reducers | 14 passed in 3.34s |
| Integrated reducers/services/missions/inbox | 57 passed in 13.02s |
| Native discipline UI | Four passed in 1.67s |
| Final full local suite | **549 passed in 53.14s**, zero failures/errors/skips; private artifact `var/m3-discipline-pytest.xml` |
| Added focused absent-Dog application regression | One passed after the full run; applies real effects without exposing the objective |
| Registry | RULES_SUBSET, 473 inventory entries, 436 required core entries; 11 subset / 462 unimplemented; zero independently verified |
| Handoff integrity | 34 required files, 86 planned cases, four schemas and four synthetic fixtures; planning package PASS only |
| Publishable-file check | 269 files, 40 original manifest entries intact, zero findings |
| Whitespace / startup wrapper | `git diff --check` and `bash -n` passed |
| Live operational readback | Exactly one bot; frozen-source hashes unchanged; live schema 0011; integrity ok and zero FK errors |

Initial test authoring found a protected-Identity fixture accidentally below the
ordinary cap, a return value needing an explicit string type, and two overlong
static UI strings. These were corrected before the passing checks. No network
access is allowed in the synthetic tests. No live migration, restart, M3 activation
or environment publication occurred. Private engine/PDFs/runtime data stay ignored.

This is a partial M3D/M3H checkpoint, not milestone acceptance. Revoked Privileges,
Strict Regulations and all four Severe Punishments need their supporting runtime
mechanics. Libido Inhibitor is stored canonically; future Sex Plays must enforce it
before release. Last-Asset context, Ankou and Void follow-ups remain blocking until
specific resolvers exist. Princess/DoctorDoctor reactions, Requisitions, remaining
playbook interactions, Strain/world mechanics and independent/human review remain.

One new source edge case needs an owner ruling: Sedation with fewer than two
remaining Identities (book PDF 17 / printed p.15). The source provides no fallback.
That branch currently fails without committing an effect; no recommendation has
been silently applied. M3 remains IN_PROGRESS / RULES_SUBSET.
