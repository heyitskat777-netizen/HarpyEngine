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


## Mission-end reactions and recovery context checkpoint

The owner approved two further campaign rulings: Sedation marks all remaining
Identities when fewer than two exist, and Princess checks Ace after its Status
promotion, gaining its own Permission separately from the later normal Ace bonus.
Both are recorded in the registry/trusted policy model, with explicit synthetic
fixture configuration. No live policy was edited. Zero/one-Identity Sedation now
requires confirmation, changes no Identity count, preserves Paired exceptions and
sets Heat to zero before any separately owned Paired Heat allocation.

New pure/service/native modules resolve DoctorDoctor's failed-Cadre-mission mark
and Princess's factual standards review before the final reward snapshot. At eight
Obsolescence boxes, canonical state marks the Frame scrapped and creates a real
owner-controlled replacement task. Mission completion, dispatch/acceptance and new
Plays cannot bypass it. DoctorDoctor's three other printed triggers have pure
reducer tests only; their actual production Plays/events are not implemented by
this checkpoint. The replacement itself is still unavailable.

Princess's assigned current Handler reviews its three recorded standards, with the
Handler standard visibly identified as an order. The review is a signed human fact,
not invented behaviour or consent. An upheld review applies Status first and the
approved post-promotion Permission. Normal completion/Ace rewards are committed
later from the final Status order. Negative reviews grant no invented benefit.
Rationale remains in private append-only work history, not generic event payloads.

Last-Girl-Asset Beating now requires a typed current-Handler context review before
continuing: outside a Frame, apply Helplessness against the inflictor; inside,
record that the outside-Frame condition does not apply. The factual context and
mechanical effect commit together. Neither a subject-submitted form nor a generic
acknowledgment can clear it. Existing explicit Helplessness recovery remains the
M2 pilot subset; this is not full Off-Duty/Defeat implementation.

`/mission reactions` and the requests inbox expose private owner-bound native
controls. Saved reads remain available during pauses; stale forms and unrelated
members cannot change state. The new service uses scoped playbook approval,
authorized current Handler identity, game/work revisions, append-only work and the
existing canonical state transaction. No independent review was fabricated.

Executed validation:

| Check | Actual result |
|---|---|
| Locked setup | 36 packages resolved, 35 installed packages checked; no dependency change |
| Pure reaction tests | Ten passed in 2.74s |
| Reaction service/native integration | Twenty passed in 4.74s |
| Combined reactions/discipline/native/inbox | 56 passed in 14.70s |
| Final full suite | **574 passed in 54.24s**, zero failures/errors/skips; `var/m3-reactions-pytest.xml` |
| Ruff lint / format | All checks passed; 193 files already formatted |
| Mypy | No issues in 103 source files |
| Registry | RULES_SUBSET: 473 inventory entries, 436 required core; 13 subset, 460 unimplemented; zero independent verification |
| Handoff verifier | 34 required files, 86 planned cases, four schemas and four synthetic fixtures; planning-only PASS |
| Publishable-file check | 276 files, 40 original manifest entries intact, zero findings |
| Whitespace / startup wrapper | `git diff --check` and `bash -n` passed |

The first full run had 573 passes and one assertion failure because the revised
Sedation validation error omitted the expected Punishment label. Restoring the
explicit label fixed it before the passing full run. Routine format/lint findings
were fixed during development. No application failure remains from those checks.

A process check found the temporary bot had stopped. Its recorded frozen source
hashes were verified unchanged, and the same tested build was restarted after its
offline policy check. Live output confirmed **Running v0.1.0** and Gateway READY,
with the existing 13-command frozen release. Live schema remained **0011**,
integrity `ok`, zero FK errors. No M3 code, migration or policy was deployed, and
no environment configuration was published. Private source/data remain ignored.

M3 remains IN_PROGRESS / RULES_SUBSET. The owner then ruled that compulsory
replacement uses a Handler-defined package, a different official Frame playbook
and no Permission charge. These are now explicit trusted-policy/registry facts,
with a detailed additive work order. Subsequent reaction/registry policy checks
passed all 18 focused tests. Actual replacement application remains unfinished;
the typed task stays pending. Remaining
Punishments, playbook interactions, full recovery, Strain/world rules and
independent/human acceptance remain unfinished; this checkpoint does not complete
M3D, M3E or M3H.


## Free, Handler-defined compulsory replacement checkpoint

The approved DoctorDoctor-scrapping path now supports player proposal, an exact
Handler-defined package and final player confirmation, with no Permission charge
and no same-playbook/alias bypass. The proposal preserves source work, Frame
instance and character identity. Revising it supersedes only its derived package
and Court requests; the original obligation remains pending. Changed state,
package, membership or Handler invalidates stale inputs. No real-time expiration
waives replacement or chooses a Frame for the player.

Packages supply an explicit zero-to-five Asset count, descriptions, damage/Void
state and only registry-available additional rules. No two-Asset baseline is assumed.
Wyvern's printed intrinsic Enormous remains within the cap. Frame-specific setup
includes owner-chosen Prince fanbase, a distinct unnamed JANUS Core baseline,
Handler-specified CONSUME hunger/Doctor track, eligible CHANGELING Strings and
separately accepted Red Queen Court allocation. A Handler-assigned AM is recorded
as a Handler Tag. These are typed baseline facts, not complete Core/Court/World
runtime mechanics. Unsupported additional abilities fail without applying a quote.
All-Void follow-up work remains explicit and cannot be acknowledged as complete.

Installation commits canonical state, saved public profile, immutable profile
snapshot, required-work history and cosmetic sync intent in one transaction.
Girl resources, existing Identities/Bonds, notes and historical receipts are
preserved; no reactivation resets anything. The current Frame's new name/appearance
is used for authorized public fields rather than the old creation snapshot.
`/mission replacement`, reaction routing and requests use native private controls.
The final review has bounded pages for the complete package, all Asset descriptions,
setup and unlocked abilities; opening it does not install anything. Court recipients
see only their own role request, not the private package or owner preferences. A
still-current request may be refused after state changes; stale acceptance remains
blocked, and refusal does not install a Frame or waive the parent obligation.

Immediate work now also blocks mission acceptance/dispatch; a pending M2 scene
Play prevents dispatch, mission end or advancement. An unresolved choice cannot
be bypassed by declaring a new mission phase. Source-specific work still remains
resumable and owner-bound.

The shared event recorder previously inherited the M1 SQL default ruleset label
for gameplay. Forward writes now stamp actual M2/M3 versions and include the
configured registry digest on M3 gameplay events. Local rebuild audit versions
are explicit as well. No old immutable record was rewritten. The replacement
integration test asserts the recorded M3 version and digest.

Validation executed:

| Check | Actual result |
|---|---|
| Final full offline suite | **600 passed in 56.65s**, zero failures/errors/skips; private artifact `var/m3-replacement-pytest.xml` |
| Added coverage | 25 pure/service/native replacement cases plus one pending-Play mission guard over the 574-test checkpoint |
| Replacement transaction tests | Ten passed in 3.31s, including origin binding, real backup/rebuild and campaign/revocation guards |
| Ruff lint / format | All checks passed; 201 files already formatted |
| Mypy | No issues in 107 source files |
| Registry | RULES_SUBSET; 473 inventory entries, 436 required core, 13 subset / 460 unimplemented; zero independent verification |
| Handoff verifier | 34 required files, 86 planned cases, four schemas and four synthetic fixtures; planning-only PASS |
| Publishable check | 283 files, all 40 original manifest entries intact, zero findings |
| Whitespace | `git diff --check` passed |

Early checks corrected a nonexistent catalogue constant, a reused synthetic
interaction key, static typing/format findings and a long-review assertion before
the final passing run. An initial full run also passed 599 tests; the suite was
rerun after correcting provenance stamping and checking stale Court refusal. No remaining check failure is hidden.
Tests perform no live Discord/network access and use synthetic data only.

The running frozen build remains separate from these edits. After its restoration
in the prior checkpoint, a further readback found exactly one bot. No M3 deployment,
live schema migration, policy edit or environment publication occurred in this
replacement work. The current live release is still the frozen 13-command build
on schema 0011; developing source registers 14 top-level groups.

M3 remains IN_PROGRESS / RULES_SUBSET. This application is tied to DoctorDoctor
scrapping; the destroyed-Frame Defeat/Off-Duty trigger is not yet implemented.
Full Frame/Core/Court abilities, remaining Punishments, recovery cycles, Strain,
world state and independent/human acceptance remain unfinished. Two upcoming
Off-Duty interpretations await owner input: DoctorDoctor's credited Permission
recipient scope and the duration of off-duty Sedation locks. Neither has been
silently applied as a production default.


## Delegated rulings and Off-Duty foundation — 2026-11-04

The owner accepted the recommended current-canonical-Pilot DoctorDoctor credit
scope and period-bounded Sedation duration, and delegated future ambiguous-rule
recommendations provided they are recorded for revision/clarification. The central
`docs/CAMPAIGN_RULINGS.md` and machine registry now distinguish explicit owner
choices from delegated interpretations, with rationale, alternatives, policy key,
revision and clarity-review status. A delegated interpretation retains a Sedation
slot lock through Tag replacement or Paired rename; explicit printed removal is
separate. Earlier explicit owner choices take precedence. No independent review,
player response or deployment permission is inferred. Pending owner rulings: none.

Added migration `0013`, private Off-Duty projection/append-only history and an
exclusive mission-or-Off-Duty required-work context. Populated mission/work upgrade
preserves all original column values and restores append-only triggers. Fresh
upgrade/check/downgrade passes on disposable data. The foundation service starts
Handler-owned preparation without inventing a mission, rejects overlapping phases,
and saves current DoctorDoctor owner's credit/no-trigger account with atomic,
exactly-once Permission effects. An absent player is not auto-answered.

Pure ordinary Go Off-Duty reducers retain 2d6 and Status rather than Heat, prohibit
repeated rolls, validate required scene participants and their own confirmations,
and apply recovery once after mandatory scene effects. Sedation scope survives
serialization/recovery and clears only at an explicit valid period end, preserving
marks. Existing M2 Flirt and repeated-Tag/Paired replacement paths cannot bypass it;
private unmark selectors exclude locked Identities. Legacy/unscoped locks fail
closed rather than silently disappearing.

This is **not a released complete Off-Duty flow**. Strain preparation has no generic
resolver or activation method; unsupported start consequences remain pending.
Handler playbook exceptions, one-use modifiers, Void Observation, optional recovery
Tag embrace, source-specific requisition/discipline/repair work, native cycle UI,
Gorgon movement and all end-of-period dependencies still need typed integration.
Pure reducers' internal completion inputs are not exposed as client waiver flags.
The explicit work/acceptance order is `docs/work_orders/M3_OFF_DUTY.md`.

Validation executed:

| Check | Actual result |
|---|---|
| Focused Off-Duty/core/service/migration tests | 20 passed in 4.70s |
| Existing M2 lock/replacement flows | 3 passed, 67 deselected in 1.87s before the final paired-slot case |
| Full offline suite | **622 passed in 69.85s**, no failures/errors/skips; `var/m3-off-duty-foundation-pytest.xml` |
| Ruff lint / format | All checks passed; 209 files already formatted |
| Mypy | No issues in 109 source files |
| Registry | RULES_SUBSET; 473 entries, 436 required core; 14 subset / 459 unimplemented; zero independent verification |
| Publishable files / original manifest | 291 files, all 40 entries intact, zero findings |
| Whitespace | `git diff --check` passed |

Initial lint found long lines, corrected before final passing checks. No automated
fixture uses live Discord/network access or real campaign data. One current bot
process was verified, with all frozen release hashes unchanged. The same tested
release was restored earlier this session and reached Gateway READY/Running v0.1.0.
No M3 live migration, command registration, private policy edit or environment
publication occurred. Development schema is 0013; live remains 0011.


## Strain scheduling and private preparation controls — 2026-11-04

Continued M3F after the Off-Duty checkpoint. Canonical GameState now holds an
explicit initial scenario, all three Low/High tracks, actual d6 receipts, chosen
columns, source-parent-linked recursive requests, repeat flags and used Endgame
slots. No scenario is guessed for existing saves. The current Handler records an
explicit complete factual start review; current Void/Frame damage and a claimed
clean successful mission are checked against canonical records. Facts awaiting a
world model remain recorded human attestations, not new world entities.

The delegated rulings register records three additional interpretations with
rationale, alternatives, implementation/change notes and clarity flags: repeat
severity switches at the next period start without rerolling; the cascade's
“other events” count uses prior selected occurrences on the same track across the
campaign; DoctorDoctor credit is recorded before the Budget start review. High
Budget then marks Obsolescence once at its resulting severity. At eight, actual
compulsory replacement retains the Off-Duty context through proposal, Handler
package and exact owner confirmation. Existing mission replacement also passes.

Each pending track roll is separately confirmed and committed before a Handler
chooses either source column. Reopening/replay does not draw again. The 72 short
column labels and 22 Endgame labels are selection aids, not completed effects.
High row 6/column 2 creates two real Low/High requests or an unused Endgame choice;
remaining queue entries survive restart and batching. Ancillary Rebel slot 3 is
unavailable without substitution. Duplicate/fabricated source parents and reused
Endgames fail closed.

Development-native `/mission strain`, `/mission off_duty`, owned DoctorDoctor
credit forms and a private Off-Duty inbox category are wired. Forms require actual
human answers/confirmation and preserve stale-state/pause/role gates. A selected
normal event or Endgame creates separate required effect work. There is no generic
resolve/waive API, and the period's Strain gate remains pending. Implementing
source-specific world/sheet effects and deferred triggers is the next dependency;
custom-event substitutions and exhausted unused-Endgame handling are also still
source/workflow gaps. See `docs/work_orders/M3_STRAIN.md`.

Validation executed:

| Check | Actual result |
|---|---|
| Pure Strain schedule/severity/selection/cascade checks | 98 passed in 0.19s before the final provenance case |
| Strain service plus mission/Off-Duty replacement regression | 18 passed in 6.56s |
| Native Strain controls and existing inbox regression | 21 passed in 4.29s |
| Combined focused scheduling/service/UI run | 110 passed in 3.81s before the final provenance case |
| Final full offline suite | **733 passed in 81.08s**, no failures/errors/skips; `var/m3-strain-scheduler-pytest.xml` |
| Ruff lint / format | All checks passed; 220 files already formatted |
| Mypy | No issues in 116 source files |
| Source registry | RULES_SUBSET; 473 entries, 436 required core; 15 subset / 458 unimplemented; zero independent verification |
| Publishable check | 302 files, all 40 original manifest entries preserved, zero findings |
| Handoff verifier | Planning-only PASS: 34 required files, 86 planned cases, four schemas/four synthetic fixtures |
| Whitespace | `git diff --check` passed |

Early static checks corrected shared record typing and line lengths. An initial
service fixture used an unlisted Wyvern spelling; its test data was corrected to
the official catalogue label, explicit Asset flags and actual replacement API
before passing. No unresolved failure is hidden. Tests are synthetic/offline.
The previous pushed Off-Duty commit `9de79ae` passed remote CI, run 41777455832.
This checkpoint introduces no further SQL migration beyond 0013. No live M3
registration, migration, policy update, environment publication or milestone
sign-off occurred. The frozen bot remains the separate running M2 release.


Implementation commits for these two checkpoints: `9de79ae` (delegated register,
period/recovery foundation, 622-test checkpoint) and `d42ca3e` (Strain scheduling,
native preparation and context-aware replacement, 733-test checkpoint).
The additive M3F-SCHED-001 case records the latter as IN_PROGRESS, not full rule
acceptance. Independent review and human Discord testing are still NOT_RUN.


## Canonical world and actual Strain consequences — 2026-11-04

The owner explicitly requested continuing until M3 implementation is finished and
ready for player testing. Work continues; this checkpoint is not the requested
final player-testing candidate, milestone sign-off or independent review.

World now lives in the existing GameState authority/history. Map setup validates
printed counts and distinct squares, hiding the initial Class 0 from players.
Typed locations/allegiances, NPC roles/controllers/Bonds, factions, Gorgons with
owned Assets/Core conditions, external Pilot custody and persistent territory
support source-specific mutations. Growth and Parasite appear as actual Types
from PDF 175–176 despite omission from the PDF 168 outline. New grid/Class-change/
revival interpretations are recorded under delegated authority with alternatives
and clarity/change notes. No previous explicit owner ruling was overridden.

Native `/mission world`, `/mission map`, `/mission npc`, `/mission npc_bond` and
private inbox/Off-Duty consequence forms are added to development source. Setup
requires explicit confirmation; private Core/Type/role records do not appear in the
player map. NPCs are actually claimed by the human playing them. Starting NPC
Bonds link only from their owner's saved slot/current character; unnamed legacy
slots can be linked later without inventing their name or copying private feelings.
World introductions cannot choose another Player's starting Bond. Native multiple
selections now survive option paging while retaining the total selection limit.

Twelve Strain branches apply actual typed initial consequences: Void Low 1/1,
2/1, 4/1, 5/1 and High 3/1; Rebellion Low 1/1, 6/1; Budget Low 5/2, 6/2 and High
2/2, 3/2, 5/1. These include real source-legal Gorgon introduction/NPC capture or
death, revived Assets/Type/Core, next-NPC affiliation with a real consumer, a real
Rebel Base, room Bonds/overflow, NPC firing, shortage Tags and political/anarchy
state. Choice ownership, exact saved rule identity, work/state revisions, current
Handler, pause and subsystem approvals remain enforced. Backend effect/work
commits roll back together and replay does not duplicate resources.

The city threat's two-use Collateral condition is stored and tested with actual
interruption/once-only completion. Gorgon Play service/scene integration remains
pending; selection or initial entity creation does not finish that subsystem.
Pure helpers cover Class Asset baselines, Sprite inheritance, guarded damage,
exposed-Core defeat, explicit one-square/period-end behavior, territory, owned
all-base-loss work and custody-required transport without automatic conversion.
World/Strain state survives actual backup and canonical history rebuild.

Validation executed:

| Check | Actual result |
|---|---|
| First pure world rules | 13 passed in 0.14s |
| World and initial Strain consequences | 35 passed in 6.42s before later UI/city hardening |
| Native world/NPC ownership regression | 10 passed in 2.70s |
| Native effect/dependent-choice controls | 2 passed in 1.46s |
| Full offline suite | **775 passed in 80.73s**, no failures/errors/skips; `var/m3-world-strain-effects-pytest.xml` |
| Post-full counter/resource hardening regression | 32 passed in 5.36s |
| Ruff / format | All checks passed; 234 Python files formatted |
| Mypy | No issues in 124 source files |
| Source registry | RULES_SUBSET; 473 entries, 436 required core; 33 subset / 440 unimplemented; zero independent verification |
| Publishable check before work-order addition | 316 files, all 40 original manifest entries intact, zero findings |

Early tests exposed unnamed saved NPCs; the import path and synthetic fixture were
corrected to support the actual existing contract rather than requiring a guessed
name. Static checks corrected typing/import/line-length findings. A followup
counter check prevents a completed threat from destroying a rebuilt city again;
new Gorgons cannot import forged previous combat conditions. All failures were
resolved by the passing checks above. Tests are synthetic and offline.

One frozen bot process was verified at the start. No M3 live migration, private
policy edit, command registration or environment publication occurred. Remaining
work, including full world combat/scene/period integration and all other core
rules, is retained in `docs/work_orders/M3_WORLD.md`; M3 stays IN_PROGRESS.

## Ordinary Off-Duty cycle and shared-roll checkpoint

M3 remains IN_PROGRESS / RULES_SUBSET. Ordinary period activation, shared locked
roll/Tag resolution, owned scene confirmations, canonical recovery/Tag embrace,
all six baseline Handler scenes, period-bound discipline, explicit Status review
and once-only world end are integrated offline. New test files are
`test_off_duty_roll_service.py`, `test_off_duty_cycle.py`,
`test_off_duty_cycle_ui.py`, `test_off_duty_discipline.py` and
`test_off_duty_handler_scenes.py` under `tests/rules/`; core recovery tests were
expanded. Actual NPC role owners can attest without gaining a Pilot sheet. Saved
M2 debts resolve only through actual typed Punishment application. World destruction
has canonical next-start Budget provenance; a factual review cannot deny it.

Executed evidence:

- Full suite: **801 passed in 98.19s**, no failures/errors/skips, artifact
  `var/m3-off-duty-cycle-pytest.xml`.
- Subsequent canonical Status/inbox refinement: **28 passed in 11.25s**.
- Strict typing: no issues in **129 source files**. Ruff check passed after
  formatting; no lint finding was suppressed.
- Registry: 473 entries, 436 required core; **35 subset / 438 unimplemented**,
  zero independent verification. The ordinary Play now has an explicit contract;
  Handler Off-Duty and core Status remain partial because interactions are unfinished.

The first full attempt had 791 passes and one failing test: its Stimulant Injection
assertion mistakenly expected five Heat. The printed implementation grants seven;
correcting that fixture led to the passing full run above. Earlier tests also
caught a synthetic event-key collision, wrong scene ID, Picker attribute and strict
fixture/type errors; these were corrected, not waived.

Correction to the earlier hosting diagnosis: the original frozen M2 bot was still
running. The ad hoc process filter missed Python's `-u` option and led to an extra
copy being started. Both tracked execution sessions were then checked. Only the
extra process was stopped with SIGTERM, after checking its module and start time;
the original process was preserved. A flag-aware check now verifies exactly one
bot. All 88 frozen-source hashes matched. The live `0011` database and private
policy were not changed; no M3 gameplay or environment publication occurred.
Process count is not a Discord/client readiness test. Session hosting remains
temporary, rather than continuous production hosting.

Void Observation, source-specific modifiers/shortages/economy, remaining playbook
and world runtime, remaining Strain/Endgame effects, independent audit and human
acceptance remain open. No ready-for-player-testing claim applies to all of M3.

Final checkpoint rerun after current-Status reads and review/permission freshness
guards: **801 passed in 102.44s**, no failures/errors/skips, replacing the current
`var/m3-off-duty-cycle-pytest.xml` artifact. Ruff passed, 245 Python files were
formatted, and mypy passed for 129 source files. The planning verifier passed;
327 publishable files retained all 40 original manifest entries with zero findings.
A Status review binds the current game revision: intervening state requires an
explicit fresh performance review, and transitions wait for acknowledged chat
permission restoration.


## Identity reset preparation and operational-check correction

Source: book PDF 10–11, 17, 28 and 58; the reset and matching-label interpretations
are recorded in `docs/CAMPAIGN_RULINGS.md` and the machine registry under delegated
authority, with alternatives and change notes. Existing explicit removal/Paired/
protected-resource decisions are preserved. Ordinary Identity slots are normalized
in a real M3 period event without adding cards or unmarking resources. Replacement
keeps the slot and active Sedation mark; explicit printed removal remains separate.
A Correctional Programming replacement previously cleared that lock and now retains
it. Runtime selectors and sheets distinguish matching labels by stable card slot.
The new pure reset reducer preserves protected extras/Paired state, restores the
actual Girl's starting set and carries scoped locks. This is preparation for
Observation, not a completed Observation command or all playbook interactions.

Executed evidence: **816 passed in 102.94s** in the full suite, artifact
`var/m3-identity-reset-pytest.xml`; later interrupted same-label Tag/reset regression
**22 passed in 6.63s**. The flag-aware process-check fixtures passed **9 tests in
0.02s**, covering `-u`, other supported Python flags and non-bot commands. The
read-only check returned one original bot. Mypy passed for 132 source files; Ruff
and format checks passed before the last operational-only tool addition. The
publishable check at that point covered 331 files, all 40 original manifest entries,
and zero findings. GitHub CI passed commit `73b6481`, run `41794354250`.

An early reset fixture mistakenly parameterized Frame catalog entries as Girls;
it was restricted to the ten base Girl entries. A moved helper import was corrected
before the passing full run. No skipped tests or waived errors are claimed.

## Frame Off-Duty reward reviews

Source cross-check: book PDF 61, 65, 68, 71, 74, 78, 81, 84 and 88;
official sheets PDF 18–26. Typed own-trigger reviews, actual Queen-holder choice
and separate Wyvern Handler-interest replies are integrated into real periods and
the native private inbox. Immutable real roll history binds Frame/holder eligibility;
late changes cannot rewrite earned ownership or restore historical resources.
Accounts, offerings and private targets stay out of generic event/outcome metadata.
Current member/Handler/character/revision/policy, pause and restored chat are
rechecked. Backend work/reward/receipt writes are atomic and replay-safe.

The Budget firing branch now also records unemployment; changing jobs alone could
otherwise leave an NPC eligible as a Foundation employee. A Handler-controlled
Director introduction is rejected: its required separately played role is still
pending. Delivery reuse is checked per actual character, without inventing a
single-contributor quota. Historical qualifying deliveries/demonstrations, full
custody and transport, Observation and wider playbook interactions remain open;
these entries are deliberately recorded as subsets.

Executed: focused **56 passed in 19.94s**; full **865 passed in 115.50s**, no failures,
errors or skips, artifact `var/m3-frame-rewards-pytest.xml`. The previous full run
had one obsolete inbox assertion (862 passed, one failed): another player now
has their own Frame task. The corrected assertion verifies that task while still
excluding the private DoctorDoctor credit. Additional native Wyvern two-owner and
Director-control regressions passed in the final full run. One restricted-shell
test process stalled during discovery and was stopped; the supported approved
execution completed normally. No test failure was waived.

Ruff, formatting (257 Python files) and mypy (135 source files) passed before the
last two tests were added. Registry: 473 entries, 436 required core, 45 subsets,
428 unimplemented and zero independently verified. CI passed `67cb560`, run
41798124946. New interpretations are listed with alternatives, rationale, future
change notes and clarity-review flags in the central rulings register and registry.
No M3 deployment, live migration, environment publication, independent audit or
human play-test is claimed. One original frozen M2 bot was observed running.

## Observation, nested consequences and separately played NPCs

Sources: book PDF 28/123/192, printed 26/121/190. The actual Handler records its
suspicion, Observation replaces the ordinary roll, and Status drops with the locked
real roll transaction. Both families of Void Assets, including damaged Assets,
set its modifier. Final saved Tag/Bond adjustments determine the actual separate
player/Handler selection counts. Choice overlap, nested Identity ownership and
populace Tag control are recorded as delegated rulings with alternatives/change
notes. Existing protected slots, Sedation, ordinary harsh discipline and mandatory
Moderate severity remain enforced. No client flag marks a mechanical effect done.

Saved owned effects, real NPC role invitations, separate appearance responses and
actual scene attestations now use native private controls and the inbox. The
Director needs a human different from the Handler; a member without a Pilot sheet
can accept the role, answer an appearance request and confirm its own scene.
Declining a role/appearance creates no fictional acceptance. Required NPC scene
controllers cannot be replaced by the Handler. Private accounts and NPC details
are excluded from generic event/command outcomes and unrelated participants.

Source review caught a mandatory Director interaction: its actual presence changes
the Handler to Girl rules. Arrival now creates separate blocking `director_presence`
work and prevents the Handler from continuing with its ordinary rule authority.
The typed rule-mode/price resolver is still required; nothing acknowledges or
waives it. Automatic world triggers/reprimands, future-period ordering, changed
NPC-controller recovery and remaining battle/last-Asset/playbook/economy interactions
also remain unfinished. The work order and source audit list these explicitly.

Executed full suite: **907 passed in 139.24s**, no failures/errors/skips;
`var/m3-observation-pytest.xml`. Final focused Observation/role run before the full
suite: **42 passed in 19.01s**, followed by the explicit Director-context guard and
positive Frame/Tag-tier cases. Ruff passed; **270 Python files** formatted; mypy
passed for **142 source files**. Planning verifier passed. Public-file check:
**352 files, all 40 original manifest entries, zero findings**. Registry: 473 entries,
436 required core, 47 subsets, 426 unimplemented, zero independently verified.

Development failures corrected before the passing run: strict assignment validation
required atomic choice/outcome construction; two fixtures had the wrong synthetic
Void baseline/projection field; resumed Tag fixtures must not answer an already
saved human again; an NPC handoff initially attempted its work row before its
foreign-key source event and now saves event then work in the same transaction.
No failed check was waived. Tests also prove rollback, exactly-once backend replay,
concurrent role responses, unrolled cancellation preserving the order, known-roll
resume preserving Status/dice, private canonical rebuild and an actual synthetic
backup/restore retaining the pending NPC question and receipt.

GitHub initially rejected the prior sanitized source push with Internal Server
Error. Retrying succeeded; CI passed `ee93568`, run 41812260571. Exactly one original
frozen M2 process was observed running (PID47656); its source deployment remains
88cd237. No live database/policy migration, M3 deployment, environment publication,
independent audit, human play-test or M3-ready claim has occurred.

## Scoped Director context and source distinction

Book PDF 192 / printed p.190: the Handler now has an actual source-reviewed Girl-rules
context with two owned ordinary starting Identities and zero Heat. It creates no
Pilot sheet, Frame, Cadre rank or mission membership. Reopening/replay cannot grant
another baseline. Overlapping Directors preserve the same resources; each actual
NPC controller records only its own departure, with no clock supplying a response.
The last departure closes the context without unmarking cards, adding Heat or
restoring an older balance. Private context views and native requests keep the
Handler's card labels from other participants.

Merely introducing/accepting an NPC role does not establish the Handler is in its
presence. The actual Handler records that presence. A completed actual Observation
scene with the Director and without the Handler can instead prove absence; a
client boolean alone cannot waive the source review. Ordinary Handler powers stay
gated during an unresolved review or active Girl-rules context. Its own actual
scene attestations have a narrow response path that grants no Handler power.
Shared Girl Play ports, Director Handler Plays/prices/phone calls, broader actor/cast
integration and other world interactions remain incomplete. See M3_DIRECTOR.md and
M3_ACTORS.md; the milestone is still RULES_SUBSET.

Source correction: the explicit instruction to use a different Director player is
High Budget 1/1, book PDF 151 / printed p.149. Generic NPC principles are broader.
The global separate-controller restriction is now clearly recorded as a delegated
campaign recommendation with an alternative and change-impact notes, rather than
presented as a universal printed rule. Overlap and exit interpretations have their
own clarity-review records. The printed start remains separate from those rulings.

Executed full suite: **920 passed in 167.53s**, no failures/errors/skips;
`var/m3-director-context-pytest.xml`. Final focused context/Observation/Handler-scene
run: **53 passed in 28.35s**. Ruff passed, **278 Python files** formatted; mypy passed
for **145 source files**. Planning verifier passed. Public check: **360 files, all
40 original manifest entries, zero findings**. Registry: 473 entries, 436 required
core, 48 subsets, 425 unimplemented, zero independently verified. Earlier typed
proof-dictionary and tuple inference errors were fixed before these passing checks.
An added regression keeps the printed Girl/Handler co-participant requirement for
harsh scenes even when an extra NPC controller is invited.

The prior Observation push again received a GitHub Internal Server Error; the
retry succeeded. CI passed `6d76c44`, run 41816188782. The original frozen bot was
observed as exactly one process; all **88 frozen source hashes matched**. No live
migration/policy change, M3 deployment, environment publication, independent review,
human play-test or M3-ready claim applies to this checkpoint.


## Actual actors, scene casting and Strict Regulations

Typed actor references now distinguish fictional identity from current human
control and bind actual character generations. Resource descriptors preserve the
actual canonical model; missing NPC/external resources stay absent. Own-role and
scene-role native selectors do not transfer secrets, traits or a Girl's scene
participation merely because the same human controls an NPC. Actual immutable
legacy bind/join/state/profile evidence proves original roles; the legacy Handler
join is a facilitator, not fictional presence. Source-bound cast joins/withdrawals,
stale-controller withdrawal, close/archive and restored-chat checks are canonical.
Mixed-role Plays remain blocked until actual actor-aware consumers are implemented.

Existing activation and Play/order/follow-through state now records character IDs.
Before dice or saved private choices apply, every actual original participant
must still be that character. Genuine legacy action history proves the original
generations without guessing; known-roll resume preserves receipts and answered
humans. A source-proven optional metadata binding does not reset resources.

Strict Regulations (PDF 17 / printed p.15) now has inflictor-owned rule/disclosure
controls, exact Moderate consultation (PDF 18 / printed p.16), private typed rules
and manual informed-Handler breach review. Concealed text is excluded from the
subject's consultation, raw sheet and unrelated projections. Every actual breach
retains a distinct event and discipline cause. Current mission/Off-Duty and next
Off-Duty timing are explicit; future debt does not block the current recovery or
silently become current work. A genuine two-period synthetic cycle proves later
required work and a real separately attested Punishment fulfill the cause once.
The recommendation, alternatives, clarity review and adjustment impact are in the
central and machine ruling registers. No passive chat or AI judges a breach.

Executed final full suite: **974 passed in 177.32s**, no failures/errors/skips;
`var/m3-actors-regulations-pytest.xml`. Focused combined discipline/cast run:
**64 passed in 24.00s**, followed by the review-disclosure and actual future-period
recovery checks: **22 passed in 9.14s**. Earlier full actor/cast baseline:
**958 passed in 179.74s**, `var/m3-actor-cast-pytest.xml`. The actor/cast first focused
run had **1 failed, 106 passed** because the rollback fixture patched another
service instance; corrected instance fault injection passed all **12 cast tests**
in 4.04s. The expanded final suite includes that correction. No failure was waived.

Final Ruff passed; **296 Python files** formatted; mypy passed for **156 source files**.
Final public source check: **378 publishable files**,
all **40 original manifest entries**, zero findings. Registry remains 473 inventory
entries, 436 required core, 48 subsets, 425 unimplemented and zero independent
verifications. This checkpoint does not finish M3. Shared actor-aware Plays,
playbooks/economy, five remaining Punishments, career/lifecycle, 60 further Strain
cells, Endgames and other world interactions still require implementation.

Exactly one original frozen M2 process was observed (PID47656); all **88 frozen
source hashes matched** at commit 88cd237. GitHub CI passed the prior Director
checkpoint 7b34541, run 41821321860. The sanitized push path now uses the existing
`gh auth git-credential` helper per command; no token, global credential setting or
environment draft was changed. No live migration/policy change, M3 deployment,
environment publication, independent/human acceptance or M3-ready claim applies.


## Low Budget repair shortage and exact optional prices

Low Budget 4/2 now saves a source-bound restriction without retroactive damage or
repair changes. The next actual dispatched mission, its real end and following
recovery period bind the effect. The next-dispatch interpretation and alternative
are recorded as a delegated clarity-review ruling. Overlapping restrictions retain
each source without granting additional free quotas. Recovery uses owner-bound
native selectors and repairs exactly one available damaged Girl and Frame Asset,
leaving other damage intact. Normal unrestricted recovery remains separate.

The current Handler quotes each optional extra Asset repair; no price is inferred.
The quote binds the real character, Frame incarnation, sheet/quote revision and
actual period/restriction. Offer/reopen/reprice never spends. The player separately
accepts or declines; charge, repair, response and history commit once together.
Old/revised prices, changed sheets/characters/Frames/Handler, insufficient funds,
pauses, pending Plays and unrestored chat block spending. Current-period closure
ends its restriction and invalidates unaccepted purchases without inventing an
answer. Pending optional quotes do not prevent actual period completion. Native
`/mission repairs` and the private guided inbox keep other users out of the quote.
Casualty body-part rules and all other Requisitions remain separate future work.

Final full suite: **988 passed in 209.11s**, no failures/errors/skips;
`var/m3-shortage-repairs-pytest.xml`. Focused mission/recovery/quote run:
**43 passed in 45.10s**, `var/m3-shortage-repairs-broad-recheck.xml`. Earlier isolated
repair run passed **11 tests in 18.87s**. Development fixture corrections are
preserved transparently: the first run had **7 failed, 3 passed** because it assumed
the old Ace Status after the actual review had made that player Dog. Fixture
review also corrected a price above the actual Permission balance before reaching
the purchase assertion. Corrected tests respect real Status and an affordable
explicit price. The first broader run had **1 failed, 42 passed**
because its unrelated pending-Play setup omitted mandatory spending of held Heat;
the corrected fixture follows that rule. No gameplay guard or failure was waived.

Ruff passed; **303 Python files** formatted; mypy passed for **160 source files**.
Registry: 473 entries, 436 required core, **50 subsets, 423 unimplemented**, zero
independent verifications. The Permissions entry now truthfully records partial
reward/paid-repair coverage, without claiming its remaining Requisitions. Public
source scan before this evidence update: **385 files**, all **40 original manifest
entries**, zero findings. The original planning package is preserved.

The prior checkpoint **772eb22722b4c7f65c643f79a932c48555fb5916** was pushed as
sanitized source; GitHub CI passed, run **41833215239**. Exactly one original frozen
M2 process remained observed (PID47656). No live migration/policy change, M3 deploy,
environment publication, independent/human acceptance or M3-ready claim applies.
Shared actor-aware Plays, playbooks/economy/careers, five Punishments, 59 remaining
Strain cells, all Endgames and other world interactions still require work.


## Random missed supply and actual pre-roll modifiers

Low Budget 3/2 now records the current Handler's actual missing resource and one
OS-backed uniform draw from the complete actual Cadre population. The canonical
assignment retains original character references, source event and period; the
Handler cannot select a recipient or redraw through replay/reopening. A separate
−2 pre-roll modifier is consumed with the actual locked roll. It is shown before
confirmation and retained separately from base Status/Void Assets and later
Tag/Bond adjustments in public-minimal and private receipts and period history.
Void Observation uses the logged delegated interpretation with an alternative and
clarity-review/change-impact notes. Private resource/population data is excluded
from generic event/command payloads and unrelated players.

Unrolled cancellation preserves the assignment; known-roll recovery retains the
same recipient, dice, penalty and prior human responses. Character replacement
before or after assignment cannot transfer the loss. Strict draw bounds, stale
inputs, explicit resource, no forged target, pause/policy, transactional rollback,
concurrency, Observation and all three tiers are covered. A real post-roll Personal
Bond adjustment retains both −2 supply and +2 Tag components. A failure after
receipt creation rolls back consumption/receipt together, without redrawing the
already committed recipient. Native input has no recipient picker and receipt
presentation shows actual base and supply arithmetic.

Full suite: **1011 passed in 252.42s**, no failures/errors/skips;
`var/m3-supply-pytest.xml`. Focused supply/ordinary/Observation run: **41 passed in
30.33s**, `var/m3-supply-broad.xml`. Subsequent focused supply run: **22 passed in
12.33s**, before the final extra before/after generation parameter; the full suite
includes both cases. Initial focused run had **1 failed, 24 passed** because the
new Observation fixture supplied its hiding flag/account in reverse order. The
fixture now supplies the real typed arguments; no implementation gate was waived.

Final Ruff passed; **310 files** formatted; mypy passed for **163 source files**.
Registry remains RULES_SUBSET: 473 entries, 436 required core, **51 subsets, 422
unimplemented**, zero independent verifications. Final source scan:
**392 files**, all **40 original manifest entries**, zero findings. Source/fixture
matrices, other temporary modifiers, remaining core Plays/playbooks/economy/careers,
five Punishments, 58 Strain cells, Endgames and world interactions remain unfinished.
The next scientific Observation work is explicitly planned in its additive order.

The sanitized prior repair checkpoint **4e30161ab927bc4644b286795e25549228eee7a2**
was pushed; GitHub CI passed, run **41837328257**. Exactly one frozen M2 bot remained
observed (PID47656); all **88 frozen source hashes matched**, source 88cd237. No live
migration, policy change, M3 deploy, environment publication, independent/human
acceptance or M3-ready claim applies. Work continues within M3.


## Scientific Observation and distinct actual order sources

Low Budget 3/1 now records the current Handler's one/two actual scientific targets
and explicit per-target hiding decisions. Typed required-order effects materialize
real Observation contexts/causes, with distinct real source events and event indexes
inside the same transaction as canonical state, period history and resolved Strain
work. Original contexts/unbound causes survive overlap, with one real roll and one
Status reduction. Character/period checks, exact target/answer ranges, stale inputs,
wrong fields, policy, pause, replay and concurrent selection retain their gates.
The selection/overlap recommendations and alternatives are centrally registered
with clarity-review and pending-order migration notes.

Resolving the Strain source alone does not grant recovery, transport, treatment,
NPC consent or a Girl response. A synthetic full two-cause Observation flow applies
an actual owned public-Tag outcome, records a scene and each human's own attestation,
then settles both actual causes. Required Frame-trigger review still precedes real
recovery. Raw dice remain one roll; ordinary Go Off-Duty remains unavailable.
The native source form requires each exact hiding answer before confirmation.

Full suite: **1029 passed in 257.16s**, no failures/errors/skips;
`var/m3-scientific-observation-pytest.xml`. The initial scientific run had **6 failed,
11 passed**: the gameplay audit wrapper defaulted every event to index zero and
could not save multiple actual sources under one command. The wrapper now accepts
explicit event indexes; child orders use distinct indexes. Rollback tests prove a
second-order failure removes all state/period/work/event changes atomically. An
expanded run had **49 passed, 1 failed** while the new recovery fixture chose a
hiding-only option after explicitly recording no hiding, then used the wrong detail
owner. It now uses a common public-Tag option and actual Handler details. The full
recovery case passed **1 test in 1.83s** before the final full suite. No authority,
source option or required recovery gate was waived to pass a fixture.

Ruff passed; **313 files** formatted; mypy passed for **164 source files**. Registry:
473 entries, 436 required core, **52 subsets, 421 unimplemented**, zero independent
verifications. Public-source scan: **395 files**, all **40 original manifest entries**,
zero findings. The milestone remains RULES_SUBSET. Five Punishments, 57 further
Strain cells, all Endgames, actor-aware core Plays, playbooks, economy/careers and
other world/scene/resource interactions still require work.

The original frozen M2 process remained observed as exactly one PID47656. No live
migration, policy change, M3 deployment, environment publication or independent/
human acceptance applies. This is another tested source checkpoint, not M3-ready.
