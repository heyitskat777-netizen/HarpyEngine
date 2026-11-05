# M3 completion audit and bounded delivery plan

Audit date: 2026-11-04. Committed baseline: `2c689fb` on `codex/m3-rules`.
Owner requested this audit after questioning the earlier 600-credit estimate.
**M3 remains RULES_SUBSET. No defensible completion percentage or credit forecast
is available.** Work resumes by finished workflows, rather than another open-ended
foundation pass. This document changes neither the agreed scope nor release gates.

The current four-agent candidate is tracked in [M3_PARALLEL_WORK.md](M3_PARALLEL_WORK.md) and the top of the acceptance report. The original audit and earlier checkpoint counts below are historical; they are not the current candidate's completion claim.

Subsequent checkpoints: **1a, Asset Installment** (`af0a221`) and **1b, Creature
Comforts** (`620e879`) are **IMPLEMENTED_AUTOMATED** within their stated flows.
Final full suite: **1,399 passed**. Independent review and human acceptance remain
pending. See [unit evidence](acceptance/m3_units.json).
The audit counts below are the original snapshot, not a recalculated percentage.

Current unit **2a is IN_PROGRESS**: human-Pilot effects, consent, native responses
and linked discipline are implemented; complete Defeat and broader actor/lifecycle
interactions still block closure. Temporary revocation/restoration now works for
implemented paid Requisitions. Last usable Frame removal has source-owned context
review and cannot waive actual Defeat. Registry now has 63 core subsets and 373
unimplemented core entries. Automated evidence is in the report; this changes no
independent or player acceptance.

## Complete features within their stated scope

“Implemented” below describes software behavior, not independent rules approval.

| Feature | Evidence and practical limit |
|---|---|
| M0 application/install/database foundation and read-only recovered-engine bridge | M0 accepted. The private recovered engine is not the bot's writable rules engine. |
| M1 server setup, saved dropdown drafts, cosmetic roles/nicknames, raw rolls, receipts/ledger and safety | Implemented. Owner confirmed the relevant Discord smoke tests. Raw rolls do not resolve official Plays. See [M1 acceptance](../reports/M1_ACCEPTANCE.md). |
| Local backup/restore, immutable history, retryable delivery and projection rebuild | Implemented and tested for the existing pilot. Rebuild is not a replacement for a full operational backup; Discord delivery can duplicate a post. |
| M2 creation/activation and guided pilot subset | Implemented for the scoped subset: five rolled Plays, Receive Orders, Brief Them, owned decisions, scenes/chat locks and recovery. Source review and broader human acceptance remain pending. See [M2 handoff](M2_REVIEW_HANDOFF.md). |

## Partial features and unfinished systems

| System | Implemented behavior | What prevents completion |
|---|---|---|
| Missions and discipline | Offers, individual answers, dispatch, rewards, absent Ace/Dog handling, consultation, selected reactions and replacement. Thirteen of seventeen Punishment routes have implementations for supported resources; one is delegation, leaving twelve direct effects with remaining interactions. | Further Requisition suspension effects, Execution, Lobotomization, Indefinite Imprisonment, Link Surgery Reversal; full lifecycle and playbook consequences. |
| Shared rules | Eight of thirteen basic entries have subsets, including ordinary Off-Duty and Observation. Mixed-role resources and saved response-chain recovery exist. | Put Someone Beneath You, Dive Deep, All Out Assault, Go For the Core, Defeat; complete targets, modifiers and consequences for existing Plays. |
| Off-Duty and economy | Ordinary/Observation flows, scenes, selected Frame rewards, repairs, Asset Installment and Creature Comforts have tested workflows. | Complete Void/medical/lifecycle consequences and every relevant playbook interaction. Privacy, Visiting Home, Retirement, Ability Unlock, Frame Grafting and Frame Swap are unfinished. |
| Playbooks and advancement | Starting choices, selected passives/tracks and reactions; corrected Frame/Class eligibility. | Complete runtimes for ten Girl, nine Frame and seven Handler playbooks, Frame/Class acquisitions, Handler advancement and extra Handler responses. A saved starting sheet is not a complete playbook implementation. |
| Physical/world actors | World records, casting, original body/Frame facts, selected Gorgon attacks/contests/Core exposure and Director context. | Actual movement/time, occupancy/link/control, transport/custody, full NPC/Gorgon/Harpy/Director effects and price/deadline enforcement. |
| Strain | Durable dice, column selection, recursion scheduling and required work. Seventeen of seventy-two cells have typed effect resolvers. | Fifty-five cells lack those resolvers; supported cells still need complete downstream coverage. Complete core Endgame effects and compulsory follow-ups are not implemented. Scheduling work does not apply its effects. |
| Lifecycle/situational rules | Selected Helpless recovery, identity reset and DoctorDoctor replacement. | Defeat/destruction, death/retirement/imprisonment, safe new-character archives, Harpy conversion, and the seven core situational entries. |
| Handler creation work in progress | Three modules plus routing edits preserved under ignored `var/parked-handler-creation-before-unit-1a/`, with file hashes and routing patch; prior lint/type checks passed. | No feature tests, canonical persona activation or starting Bond/rank application. Excluded from completed work and active unit changes. |

The original audit registry had **436 required core entries: 62 subset, 374 unimplemented,
zero declared fully implemented**, with independent review pending. There are also
37 deferred Ancillary entries. These inventory units mix headings, entire systems,
Plays and table cells; some broad entries still say unimplemented despite tested
subflows. They are not equal-size tasks and cannot produce a reliable percentage.
Only eight core entries currently carry full contract objects; seven are marked
source-audited. The acceptance tracker has **44 cases: 27 IN_PROGRESS, 17 NOT_RUN**.

The original audit full-suite artifact records **1,374 tests, zero failures/errors/
skips**, in 414.360 seconds (`var/m3-frame-classification-pytest.xml`). This is prior
committed-candidate evidence, not a fresh run against the untested Handler edits,
a coverage percentage, or proof that an entire M3 acceptance case passed.

## Bounded deliverables

The rows below are an ordered backlog, not equal-size estimates. A group containing
several units is not one implementation job. Before starting each unit, freeze its
source branches, exact completion tests and dependencies. Finish or explicitly
report that unit blocked before starting another. Never hide a missing effect
behind generic acknowledgement or a permanently pending follow-up.

| Order | Independently reviewable units | Completion demonstration |
|---|---|---|
| 1 — Close existing purchase workflows | Two units: Asset Installment; Creature Comforts. Audit their exact source branches and existing tests, fill actual gaps, record implemented subflow evidence. Keep the broader Requisitions entry partial. | Owned purchase → payment → actual Asset or qualifying roll/scene → exact grant/decline → readable receipt after restart. Reuse existing implementations; no redesign. |
| 2 — Finish social rules | One unit each for Put Someone Beneath You and Dive Deep, including their actual Status/Bond/Tag changes and required responses. | Two actual characters complete every result branch with legal ranks, owned choices and durable changed resources. Complete affected existing shared-rule consumers. |
| 3 — Finish original Handler creation | One creation workflow covering seven printed starting variants: persona identity, descriptions, two gear choices, starting Bond/rank choices and required agreements. Reuse or repair the parked draft only if it passes review. | Save/reopen → actual human choices → explicit canonical creation; existing M2 resources/history preserved. Appointment/account/profile remain distinct. Gear descriptions do not spawn NPCs or grant transport. Playbook runtimes remain separate units below. |
| 4 — Finish physical operations and lifecycle | Separate named operations: movement/fictional time; cockpit/link/control; transport/custody; original-character archival/replacement. Death, retirement and imprisonment use this same identity-preserving path. | An actual actor moves or changes control/career through source-legal steps; original body, Frame, resources, obligations and history remain attached to the right character. Old forms cannot act as its replacement. |
| 5 — Finish combat and recovery | One shared Play per unit: All Out Assault, Go For the Core, Defeat. Separate source-defined medical, Helpless and Void-threshold/conversion workflows as required dependencies. | Attack → actual damage/Core outcome → Defeat → owned consequence → medical/recovery or archived character. Test all tiers, final Assets, body/Frame context and supported target roles. A queued missing consequence does not pass. |
| 6 — Finish remaining economy and discipline | One unit per six missing standard Requisitions and five unsupported Punishments listed above. Implement dependency operations first; validate existing eleven effects and delegation against them. | Pay/apply → all actual effects → any restoration/replacement/retirement → consistent sheet and history. Wrong owner, stale quote, insufficient funds and pause cannot charge or apply effects. |
| 7 — Finish playbooks and Handler rules | One full playbook per unit, 26 total. Include base rules, special tracks, its acquired rules and complete starting/runtime interactions. Separate units for thirteen Class Requisitions, each Handler advancement, and each remaining basic Handler response. | A source checklist for that unit has no unsupported branch. Test passive plus active effects, acquisition, consumption/expiry and interactions with shared Plays. Selecting a playbook or recording a counter does not pass. |
| 8 — Finish world and situational rules | One named actor role/type or situational rule per unit: NPC, Gorgon/type, Harpy, Director, Expanded Status, Lobotomy, Escape, Voidspace Invasion, Captured, Timeskip and Conditioning. | Actual entity → its legal Play → price/obligation → due/breach or valid completion. Harpy treatment, transport and Core consent remain distinct. Resolve any earlier role-dependent combat branch here. |
| 9 — Finish Strain effects | One remaining cell or enabled Endgame per unit, including its full downstream consequences. Then close each of six Low/High sections (twelve cells each). There are 22 inventoried Endgame slots; 21 are core, one is deferred Ancillary. | Actual trigger/die/column → exact world/sheet changes → every immediate or future obligation reaches its real supported endpoint. Include Budget recursion and escaped-prisoner escalation. No slot reuse, lost work or unsupported “done.” |
| 10 — Assemble the M3 candidate | Consolidate source contracts, integration traces, upgrade/restore/rebuild, private projections and native controls. Then independent rules review, agreed Discord/mobile tests and owner review. | New synthetic group completes creation → mission/Plays → all consequences → Off-Duty → next mission, plus source-specific edge traces. Every required core branch is accounted for; findings and human acceptance are recorded separately. |

This sequence is a priority order, not permission to implement around unresolved
dependencies. Freeze the smallest required dependency with its consuming unit;
if it belongs to a later row, complete that named unit first and record the change
in order. Full system completion waits for its whole branch/interaction checklist.
AI, M4 onward and the optional Ancillary module remain outside this plan.

## Exit criteria and spending discipline

Each unit must deliver the actual reducer, transactional service, Discord/inbox
path, source contract and relevant synthetic tests together. Show its final player
flow, exact changed mechanics, test result, remaining dependencies and review
status. Test owner authority, campaign separation, stale/replayed submissions,
pause, interruption/restart and private views where the unit touches them.

Use focused tests during development and the required broader checks at a unit
checkpoint; repeat only after a relevant change or failure. Documentation records
evidence and decisions; it must not become a substitute for delivering the flow.
Do not invent new frameworks or expand another subsystem during a unit without
identifying the exact rule dependency. Keep the bot off and do not deploy M3 or
publish the environment as part of this audit.

Track progress as **named units completed / blocked / remaining**, with acceptance
branches as the denominator inside each unit. Do not average these unequal units
into a project percentage. Billing is not exposed here, so no replacement credit
promise is made. Actual per-unit cost, if supplied by the owner, can support a later
forecast; tests, lines of code and registry entry counts cannot substitute for it.

Next implementation: **unit 2a, Put Someone Beneath You**, followed by Dive Deep as
unit 2b. Each must complete its printed trigger, legal target, exact choices,
Status/Bond/Tag consequences, human responses, Discord flow and durable state.
The first two purchase units are closed for automated implementation; other
Requisitions and their interactions remain separate outstanding units.

Evidence sources: [source registry](../rules/registry.json),
[acceptance tracker](acceptance/m3_rules.json),
[M3 report](../reports/M3_ACCEPTANCE.md), [remaining scope](M3_REMAINING_WORK.md),
and the implementations/tests linked from those records. Current process probe:
**zero bot processes**. Historical readiness reports describe earlier operation.
