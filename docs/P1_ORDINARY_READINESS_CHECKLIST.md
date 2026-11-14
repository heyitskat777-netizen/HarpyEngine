> Historical r259/r260 review below. Current source, rulings, concrete closures and
> remaining gates are tracked in [the active queue](P1_CURRENT_QUEUE.md) and
> [integrated coverage](R285_TYPE_COVERAGE.csv). Do not restart superseded gaps
> solely from unchecked historical rows.

# P1 ordinary-workflow readiness checklist — r259 baseline / r260 planning

## Scope and evidence discipline

Baseline: verified Space r259 v28; archive SHA-256 `bab0894528ed706f16c53a31de2cc285e2e1d9e5619337060c8fedbde97d169f`. This is a finite **review checklist**, not a certification of all printed combinations. Read-only reconciliation performed 2026-11-13; no pytest run by this reviewer. Current r260 candidate changes are intentionally not pre-credited.

**IU** = native implementation and authored test entry points inspected/present, but the entire row is not independently demonstrated on this exact candidate. **FT** = only the explicitly named focused workflow has retained passing evidence; it does not upgrade a whole type. **U** = an explicitly unsupported path. **Decision** = eligibility/interpretation must be resolved before implementing a real consumer. No “all ordinary paths complete” status is assigned.

Each row closes only after its ordinary printed result branches and immediate consequences are reconciled to concrete source, saved state and native Inbox/owned choices. Presence of a module or test is not execution evidence. Cross-body/counterpart exceptions must be classified explicitly, not silently counted as either ordinary or deferred.

## Per-type finite review queue

Paths below are relative to `source/`; short service/test names retain their full directories in the listed paths. The older `docs/acceptance/p1_type_coverage.json` supplied catalog labels/source references only; its `40b3b22` statuses and heading-level “unimplemented” entries were **not** reused.

### Girl: Princess — IU
- Retained rule locators (not newly reopened PDFs): rulebook PDF 31 / printed 29; rulebook PDF 32 / printed 30; rulebook PDF 33 / printed 31.
- Ordinary workflow group to close: Standards/mission consequences; Sex result and counterpart; Show Dog directive.
- Production evidence: `src/girlframe/services/m3_princess_sex.py`, `src/girlframe/services/m3_show_dog.py`.
- Authored test entry points (not rerun): `tests/rules/test_princess_sex.py`, `tests/rules/test_show_dog.py`.
- [ ] Reconcile ordinary result branches and immediate consequences to exact source/rule references.
- [ ] Establish exact-candidate native choice/Inbox and saved-state evidence; preserve unsupported variants explicitly.
- Current boundary: no whole missing playbook established; absence of a listed blocker is not proof all interactions are implemented.

### Girl: Mockingbird — IU
- Retained rule locators (not newly reopened PDFs): rulebook PDF 34 / printed 32; rulebook PDF 35 / printed 33; rulebook PDF 36 / printed 34.
- Ordinary workflow group to close: Person/social conditions; Call of the Void; Risk Factor; Sex and group consent.
- Production evidence: `src/girlframe/services/m3_mockingbird_plays.py`, `src/girlframe/services/m3_mockingbird_sex.py`.
- Authored test entry points (not rerun): `tests/rules/test_mockingbird_sex_closure.py`, `tests/rules/test_mockingbird_communion.py`.
- [ ] Reconcile ordinary result branches and immediate consequences to exact source/rule references.
- [ ] Establish exact-candidate native choice/Inbox and saved-state evidence; preserve unsupported variants explicitly.
- Current boundary: no whole missing playbook established; absence of a listed blocker is not proof all interactions are implemented.

### Girl: Stim-Blissed — IU
- Retained rule locators (not newly reopened PDFs): rulebook PDF 37 / printed 35; rulebook PDF 38 / printed 36; rulebook PDF 39 / printed 37.
- Ordinary workflow group to close: Dose Up; Disposable Psyche; Malleable; Sex result.
- Production evidence: `src/girlframe/services/m3_dose_up.py`, `src/girlframe/services/m3_stim_sex.py`, `src/girlframe/services/m3_malleable.py`.
- Authored test entry points (not rerun): `tests/rules/test_stim_sex.py`, `tests/rules/test_disposable_psyche.py`, `tests/rules/test_malleable.py`.
- [ ] Reconcile ordinary result branches and immediate consequences to exact source/rule references.
- [ ] Establish exact-candidate native choice/Inbox and saved-state evidence; preserve unsupported variants explicitly.
- Current boundary: no whole missing playbook established; absence of a listed blocker is not proof all interactions are implemented.

### Girl: Newgirl — IU
- Retained rule locators (not newly reopened PDFs): rulebook PDF 40 / printed 38; rulebook PDF 41 / printed 39; rulebook PDF 42 / printed 40.
- Ordinary workflow group to close: Easy Target; Trainee/Mentor; Sex and owned counterpart.
- Production evidence: `src/girlframe/services/m3_trainee.py`, `src/girlframe/services/m3_easy_target.py`, `src/girlframe/services/m3_newgirl_sex.py`.
- Authored test entry points (not rerun): `tests/rules/test_trainee.py`, `tests/rules/test_easy_target.py`, `tests/rules/test_newgirl_sex.py`.
- [ ] Reconcile ordinary result branches and immediate consequences to exact source/rule references.
- [ ] Establish exact-candidate native choice/Inbox and saved-state evidence; preserve unsupported variants explicitly.
- Current boundary: Native Bonded-owned accepted-child withdrawal remains unsupported in this frozen baseline; current r260 worker must be evaluated separately.

### Girl: Casualty — IU
- Retained rule locators (not newly reopened PDFs): rulebook PDF 43 / printed 41; rulebook PDF 44 / printed 42.
- Ordinary workflow group to close: Body/hardware provenance; resistance; Sex; Wounded God; replacement.
- Production evidence: `src/girlframe/services/m3_casualty.py`, `src/girlframe/services/m3_casualty_support.py`, `src/girlframe/services/m3_casualty_replacement.py`.
- Authored test entry points (not rerun): `tests/rules/test_casualty.py`, `tests/rules/test_casualty_replacement.py`.
- [ ] Reconcile ordinary result branches and immediate consequences to exact source/rule references.
- [ ] Establish exact-candidate native choice/Inbox and saved-state evidence; preserve unsupported variants explicitly.
- Current boundary: FT only for exact native Bonded refusal/unused withdrawal after genuine transition in r259. Broader body outcomes IU.

### Girl: Oldgen — IU
- Retained rule locators (not newly reopened PDFs): rulebook PDF 45 / printed 43; rulebook PDF 46 / printed 44; rulebook PDF 47 / printed 45.
- Ordinary workflow group to close: Maxims/advice; Sex result and rewrite.
- Production evidence: `src/girlframe/services/m3_oldgen.py`, `src/girlframe/services/m3_oldgen_sex.py`.
- Authored test entry points (not rerun): `tests/rules/test_oldgen.py`, `tests/rules/test_oldgen_sex.py`.
- [ ] Reconcile ordinary result branches and immediate consequences to exact source/rule references.
- [ ] Establish exact-candidate native choice/Inbox and saved-state evidence; preserve unsupported variants explicitly.
- Current boundary: U: NPC Status outcome explicitly pauses, m3_oldgen_sex.py:699–703; no rank mutation invented.

### Girl: Vatgrown — IU
- Retained rule locators (not newly reopened PDFs): rulebook PDF 48 / printed 46; rulebook PDF 49 / printed 47; rulebook PDF 50 / printed 48.
- Ordinary workflow group to close: DNA and restrictions; Sex/learning; Unassuming Doll; travel/body persistence.
- Production evidence: `src/girlframe/services/m3_vatgrown.py`, `src/girlframe/services/m3_vatgrown_plays.py`, `src/girlframe/services/m3_offered_girl_requisitions.py`.
- Authored test entry points (not rerun): `tests/rules/test_vatgrown.py`, `tests/rules/test_vatgrown_plays.py`, `tests/rules/test_vatgrown_dna.py`.
- [ ] Reconcile ordinary result branches and immediate consequences to exact source/rule references.
- [ ] Establish exact-candidate native choice/Inbox and saved-state evidence; preserve unsupported variants explicitly.
- Current boundary: no whole missing playbook established; absence of a listed blocker is not proof all interactions are implemented.

### Girl: Alpha — IU
- Retained rule locators (not newly reopened PDFs): rulebook PDF 51 / printed 49; rulebook PDF 52 / printed 50; rulebook PDF 53 / printed 51.
- Ordinary workflow group to close: Brutalize; combat/Hound consequences; Sex and owned counterpart.
- Production evidence: `src/girlframe/services/m3_alpha.py`, `src/girlframe/services/m3_alpha_sex.py`.
- Authored test entry points (not rerun): `tests/rules/test_alpha_brutalize.py`, `tests/rules/test_alpha_sex.py`, `tests/rules/test_alpha_hound_status_review.py`.
- [ ] Reconcile ordinary result branches and immediate consequences to exact source/rule references.
- [ ] Establish exact-candidate native choice/Inbox and saved-state evidence; preserve unsupported variants explicitly.
- Current boundary: Native Bonded-owned accepted-child withdrawal remains unsupported in this frozen baseline; current r260 worker must be evaluated separately.

### Girl: AM — IU
- Retained rule locators (not newly reopened PDFs): rulebook PDF 54 / printed 52; rulebook PDF 55 / printed 53; rulebook PDF 56 / printed 54.
- Ordinary workflow group to close: Jailbroken; Scrutinized; Just Code; Sex; body/circuit/record persistence.
- Production evidence: `src/girlframe/services/m3_am_body.py`, `src/girlframe/services/m3_am_code.py`, `src/girlframe/services/m3_am_branch.py`.
- Authored test entry points (not rerun): `tests/rules/test_am_body.py`, `tests/rules/test_am_code.py`, `tests/rules/test_am_branch.py`.
- [ ] Reconcile ordinary result branches and immediate consequences to exact source/rule references.
- [ ] Establish exact-candidate native choice/Inbox and saved-state evidence; preserve unsupported variants explicitly.
- Current boundary: U/decision: learned Scrutinized/Just Code lack eligible learning consumer; native AM paths are present. Do not equate native and learned routes.

### Girl: Bonded — IU
- Retained rule locators (not newly reopened PDFs): rulebook PDF 57 / printed 55; rulebook PDF 58 / printed 56; rulebook PDF 59 / printed 57.
- Ordinary workflow group to close: Pair consent; Always By Her Side; delegation/group; Sex and source release.
- Production evidence: `src/girlframe/services/m3_bonded.py`, `src/girlframe/services/m3_bonded_support.py`, `src/girlframe/services/p1_source_pause.py`.
- Authored test entry points (not rerun): `tests/rules/test_bonded.py`, `tests/rules/test_bonded_am.py`, `tests/rules/test_bonded_rejection.py`.
- [ ] Reconcile ordinary result branches and immediate consequences to exact source/rule references.
- [ ] Establish exact-candidate native choice/Inbox and saved-state evidence; preserve unsupported variants explicitly.
- Current boundary: FT r259 Casualty release only; remaining counterpart/lifecycle combinations not certified.

### Frame: The Prince — IU
- Retained rule locators (not newly reopened PDFs): rulebook PDF 61 / printed 59; rulebook PDF 62 / printed 60; rulebook PDF 63 / printed 61; rulebook PDF 64 / printed 62.
- Ordinary workflow group to close: Performer; Fanbase; Permission/owned effects.
- Production evidence: `src/girlframe/engine/m3_frame_rewards.py`, `src/girlframe/engine/frame_setup.py`, `src/girlframe/services/m3_prince.py`.
- Authored test entry points (not rerun): `tests/rules/test_frame_rewards.py`, `tests/rules/test_frame_reward_service.py`, `tests/rules/test_prince.py`.
- [ ] Reconcile ordinary result branches and immediate consequences to exact source/rule references.
- [ ] Establish exact-candidate native choice/Inbox and saved-state evidence; preserve unsupported variants explicitly.
- Current boundary: no whole missing playbook established; absence of a listed blocker is not proof all interactions are implemented.

### Frame: CONSUME — IU
- Retained rule locators (not newly reopened PDFs): rulebook PDF 65 / printed 63; rulebook PDF 66 / printed 64; rulebook PDF 67 / printed 65.
- Ordinary workflow group to close: Starvation/Hunger; Eat; Feral; Let Us Partake/regrowth.
- Production evidence: `src/girlframe/engine/frame_setup.py`, `src/girlframe/engine/m3_frame_rewards.py`, `src/girlframe/services/m3_consume.py`.
- Authored test entry points (not rerun): `tests/rules/test_frame_rewards.py`, `tests/rules/test_frame_reward_service.py`, `tests/rules/test_consume.py`.
- [ ] Reconcile ordinary result branches and immediate consequences to exact source/rule references.
- [ ] Establish exact-candidate native choice/Inbox and saved-state evidence; preserve unsupported variants explicitly.
- Current boundary: U: actual Clone AM copy consumption needs same-copy lifecycle, m3_consume_support.py:170–173.

### Frame: JANUS — IU
- Retained rule locators (not newly reopened PDFs): rulebook PDF 68 / printed 66; rulebook PDF 69 / printed 67; rulebook PDF 70 / printed 68.
- Ordinary workflow group to close: Harpy Core; Living Battery; PANDORA; training; plug/storage.
- Production evidence: `src/girlframe/services/m3_janus.py`, `src/girlframe/services/m3_janus_storage.py`.
- Authored test entry points (not rerun): `tests/rules/test_janus_core_service.py`, `tests/rules/test_janus_battery.py`, `tests/rules/test_janus_control_lifecycle.py`.
- [ ] Reconcile ordinary result branches and immediate consequences to exact source/rule references.
- [ ] Establish exact-candidate native choice/Inbox and saved-state evidence; preserve unsupported variants explicitly.
- Current boundary: no whole missing playbook established; absence of a listed blocker is not proof all interactions are implemented.

### Frame: JANUS-B — IU
- Retained rule locators (not newly reopened PDFs): rulebook PDF 68 / printed 66; rulebook PDF 69 / printed 67; rulebook PDF 70 / printed 68.
- Ordinary workflow group to close: Uses official JANUS workflow; label/creation mapping must remain consistent.
- Production evidence: `src/girlframe/engine/creation.py`, `src/girlframe/engine/frame_classes.py`.
- Authored test entry points (not rerun): `tests/rules/test_janus_requisitions.py`, `tests/rules/test_janus_storage.py`.
- [ ] Reconcile ordinary result branches and immediate consequences to exact source/rule references.
- [ ] Establish exact-candidate native choice/Inbox and saved-state evidence; preserve unsupported variants explicitly.
- Current boundary: Alias of JANUS, not an independent ruleset or extra completion unit.

### Frame: DoctorDoctor Mk. II — IU
- Retained rule locators (not newly reopened PDFs): rulebook PDF 71 / printed 69; rulebook PDF 72 / printed 70; rulebook PDF 73 / printed 71.
- Ordinary workflow group to close: Nanobot Injection; Borrowed Wings; support and replacement.
- Production evidence: `src/girlframe/services/m3_doctor.py`.
- Authored test entry points (not rerun): `tests/rules/test_doctor_runtime.py`, `tests/rules/test_replacement_service.py`.
- [ ] Reconcile ordinary result branches and immediate consequences to exact source/rule references.
- [ ] Establish exact-candidate native choice/Inbox and saved-state evidence; preserve unsupported variants explicitly.
- Current boundary: FT: unsupported NPC GM-request and donor Wings→owned Void task only. NPC treatment mechanics U; final donor Void/return IU; graft-side full-Void U.

### Frame: Wyvern 0.4 — IU
- Retained rule locators (not newly reopened PDFs): rulebook PDF 74 / printed 72; rulebook PDF 75 / printed 73; rulebook PDF 76 / printed 74; rulebook PDF 77 / printed 75.
- Ordinary workflow group to close: Exploration; body/cargo roles; combat effects and Permission.
- Production evidence: `src/girlframe/services/m3_wyvern.py`, `src/girlframe/services/m3_wyvern_support.py`, `src/girlframe/services/m3_wyvern_combat.py`.
- Authored test entry points (not rerun): `tests/rules/test_wyvern.py`, `tests/rules/test_wyvern_combat.py`.
- [ ] Reconcile ordinary result branches and immediate consequences to exact source/rule references.
- [ ] Establish exact-candidate native choice/Inbox and saved-state evidence; preserve unsupported variants explicitly.
- Current boundary: no whole missing playbook established; absence of a listed blocker is not proof all interactions are implemented.

### Frame: The Enforcer — IU
- Retained rule locators (not newly reopened PDFs): rulebook PDF 78 / printed 76; rulebook PDF 79 / printed 77; rulebook PDF 80 / printed 78.
- Ordinary workflow group to close: Conditioning; Enforcement Initiative; custody/discipline; firearm.
- Production evidence: `src/girlframe/services/m3_enforcement_initiative.py`, `src/girlframe/services/m3_enforcer_requisitions.py`.
- Authored test entry points (not rerun): `tests/rules/test_enforcer_conditioning.py`, `tests/rules/test_enforcer_director_judge.py`, `tests/rules/test_compliance_virus.py`.
- [ ] Reconcile ordinary result branches and immediate consequences to exact source/rule references.
- [ ] Establish exact-candidate native choice/Inbox and saved-state evidence; preserve unsupported variants explicitly.
- Current boundary: no whole missing playbook established; absence of a listed blocker is not proof all interactions are implemented.

### Frame: CHANGELING — IU
- Retained rule locators (not newly reopened PDFs): rulebook PDF 81 / printed 79; rulebook PDF 82 / printed 80; rulebook PDF 83 / printed 81.
- Ordinary workflow group to close: Blank Slate; Fingers; Psych Strings; body/mental consequences.
- Production evidence: `src/girlframe/engine/frame_setup.py`, `src/girlframe/engine/m3_frame_rewards.py`, `src/girlframe/engine/m3_changeling.py`.
- Authored test entry points (not rerun): `tests/rules/test_frame_rewards.py`, `tests/rules/test_frame_reward_service.py`, `tests/rules/test_changeling.py`.
- [ ] Reconcile ordinary result branches and immediate consequences to exact source/rule references.
- [ ] Establish exact-candidate native choice/Inbox and saved-state evidence; preserve unsupported variants explicitly.
- Current boundary: U: Blank Slate active Clone additional Identity, m3_changeling_identity.py:55–63. Finite Sex counterpart adapters remain; current r260 worker separate.

### Frame: Project Ankou — IU
- Retained rule locators (not newly reopened PDFs): rulebook PDF 84 / printed 82; rulebook PDF 85 / printed 83; rulebook PDF 86 / printed 84; rulebook PDF 87 / printed 85.
- Ordinary workflow group to close: Feedback; Emotional Relay; Processor; owned source consequences.
- Production evidence: `src/girlframe/services/m3_ankou_feedback.py`, `src/girlframe/engine/m3_ankou.py`, `src/girlframe/services/m3_ankou.py`.
- Authored test entry points (not rerun): `tests/rules/test_ankou_feedback.py`, `tests/rules/test_frame_rewards.py`, `tests/rules/test_ankou.py`.
- [ ] Reconcile ordinary result branches and immediate consequences to exact source/rule references.
- [ ] Establish exact-candidate native choice/Inbox and saved-state evidence; preserve unsupported variants explicitly.
- Current boundary: no whole missing playbook established; absence of a listed blocker is not proof all interactions are implemented.

### Frame: The Red Queen — IU
- Retained rule locators (not newly reopened PDFs): rulebook PDF 88 / printed 86; rulebook PDF 89 / printed 87; rulebook PDF 90 / printed 88; rulebook PDF 91 / printed 89.
- Ordinary workflow group to close: Court; AM Transfer; Consult; owned Court effects.
- Production evidence: `src/girlframe/services/shared_setup.py`, `src/girlframe/services/m3_frame_swap.py`, `src/girlframe/engine/m3_red_queen.py`.
- Authored test entry points (not rerun): `tests/rules/test_frame_swap_service.py`, `tests/rules/test_replacement_service.py`, `tests/rules/test_frame_reward_service.py`.
- [ ] Reconcile ordinary result branches and immediate consequences to exact source/rule references.
- [ ] Establish exact-candidate native choice/Inbox and saved-state evidence; preserve unsupported variants explicitly.
- Current boundary: no whole missing playbook established; absence of a listed blocker is not proof all interactions are implemented.

## Focused evidence already retained (do not rerun merely to count passes)

- **FT — Check Sensors:** exact printed questions/readable wording; `prior-r236-evidence/sensor-root-targeted.log`, 13 focused passes. Not published; not all basic Plays evidence.
- **FT — r259 bridges:** `r259-evidence/ROOT-REPORTED-FOCUSED-RESULTS.json`: combined 3 passed in 13.47s for `test_native_bonded_casualty_release.py`, `test_doctor_npc_gm_bridge.py`, `test_doctor_wings_void.py`. Initial Casualty fixture failures retained. GM handoff is not treatment completion; owned Void task is not final Void/loan-return completion.
- **FT — representative session/native bridge:** r257 and r258 evidence preserves mission→Play→discipline→Strain→Off-Duty→next mission and native callback tests. Mock Discord and bounded service-driven portions; not every type or live guild delivery.

## Concrete development/decision queue (baseline only)

1. Native Bonded→Newgirl/Alpha unused accepted-child owner withdrawal; preserve exact parent/child and psychic exclusions.
2. Oldgen NPC Status consequence: explicit GM/rules semantics plus real supported state, or retain honest unresolved request.
3. Clone identity/copy lifecycle for CHANGELING Blank Slate and CONSUME; no fiction-only deletion/completion.
4. Doctor NPC treatment mechanical consumers; donor Wings final Void/return verification; graft-side full-Void handling.
5. Source-specific CHANGELING counterpart gaps, prioritized only when ordinary cohort encounters require them.
6. Eligible learning of AM Scrutinized/Just Code: rules-backed decision, then actual circuit/adjusted-body consumer if allowed.

## Release gates (all pending unless separately evidenced)

- [ ] Replace stale type-level status claims with completed ordinary branch evidence, not module counts.
- [ ] Reconcile isolated cumulative package with potential pre-pause unpublished checkout; no destructive overwrite.
- [ ] Freeze exact candidate and run final full regression, global static/registry checks, migration/privacy/backup/restore/restart checks.
- [ ] Independent rules/clarity review; documented unsupported outcomes and durable GM escalation preserving mandatory effects.
- [ ] Private Discord configuration/roles/database/secure token and matching registry/scoped approval; separate deployment permission. Bot remains OFF.
- [ ] Actual human playtest and owner acceptance. AI Director is not prerequisite for human-led P1.

Published provenance remains `b265003783c0870c6b8fd855a836010380d11b89`, 2026-11-09 05:22:30 UTC. r259 is isolated/unpublished; pre-pause checkout unverified. No completion percentage can be derived from these unequal rows.
