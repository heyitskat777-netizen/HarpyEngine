# M3 remaining work — verified development snapshot

M3 is **IN_PROGRESS / RULES_SUBSET** and is not ready for full player testing.
This snapshot separates implemented workflows from remaining agreed scope; it
does not narrow the milestone.

The current four-agent implementation map is [M3_PARALLEL_WORK.md](M3_PARALLEL_WORK.md). It supersedes older per-feature statements below. The latest combat/Harpy/original-person candidate passes **1,983 automated tests**; the earlier `e9e528b` / 1,796-test checkpoint is historical. M3 remains incomplete and work continues.

The owner's subsequent cost/progress review is recorded in
[the completion audit and bounded delivery plan](M3_COMPLETION_AUDIT.md).
Use that plan for future implementation units. The bot is intentionally off at
the owner's request; do not restart it automatically. Handler creation now has source-bound automated evidence; the old parked draft remains historical, not a separate tested feature.

Bounded units **1a (Asset Installment)** and **1b (Creature Comforts)** are now
implemented for their purchase/benefit/receipt flows. Final automated checkpoint:
**1,399 tests passed**, code `620e879` (1a code `af0a221`).
See [unit contracts/evidence](acceptance/m3_units.json). Broader Requisitions,
independent review and human acceptance remain unfinished.

Unit **2a remains IN_PROGRESS**. Current human-Pilot social choices, consent-locked
Tags, owned pin/child-Play responses and actual on-scene discipline have focused
evidence. Implemented paid Requisitions now have temporary suspension/restoration.
Last usable Frame removal requires actual context review; piloting battle loss
keeps real Defeat work pending. Complete Defeat, broader actor targets and cross-rule
consequences before closing this unit. See the current acceptance report for the
latest candidate's checks; the 1,399-test result below is the unit-1b baseline.

Current integrated candidate: **1,983 automated tests passed** (`var/m3-combat-harpy-full-fixed.xml`). Unit 2a remains
IN_PROGRESS and does not change independent/player acceptance.

The registry contains 473 source/table entries: **436 required core entries** and
37 deferred Ancillary entries. Of the required core, **81 are partial and 355 are
unimplemented**. None is independently approved. Entries are inventory units,
not equal-size coding tasks or a completion percentage. The acceptance tracker
currently has 44 cases: 27 in progress and 17 not run, with no completed milestone
acceptance. Existing automated tests do not imply those full cases passed.

Unit-1b baseline full test artifact: **1399 tests, zero failures/errors/skips**,
`var/m3-unit-1b-full-final.xml`. See `reports/M3_ACCEPTANCE.md` for commands,
earlier failures/corrections, checks and the difference from human acceptance.

| Package | Remaining completion work |
|---|---|
| M3A — source audit | Finish nested branches, book/sheet comparisons, dependency contracts and the M2 cross-rule audit. Frame categories/aliases are corrected; the overall branch audit remains pending. |
| M3B — shared rules | Finish broader social/role consumers, Engage's remaining actual consequences and Harpy extras. Dive/Defeat and Pilot combat now have source-bound candidates; complete collateral, Gorgon branches, broader target/tier coverage, remaining original-ending callbacks and all affected actual actor/resource ports before ungating whole combat. |
| M3C — playbooks | Complete all ten Girl, nine Frame and seven Handler runtimes: passives, Plays, counters, special resources, control/Core/AM interactions, temporary effects and acquisition consequences. Handler creation and fresh persona generations are implemented; remaining runtime abilities are not. |
| M3D — economy/discipline | Privacy/Home/Retirement and the four severe discipline workflows now have bounded automated evidence. Finish remaining Unlock/Grafting destinations, full Frame Swap runtime consumers, future benefit suspension and broader role-specific discipline. Preserve actual original character/persona ownership through every source continuation. |
| M3E — recovery/lifecycle | Core original-character archives, medical/Void/Defeat, free replacement and returned-original obligations are implemented within their documented scopes. Finish remaining role/playbook follow-ups, inherited mandatory Harpy Dive, Harpy Off-Duty, source-ended continuing fight, archived killer Tags and exact pending procedures after body changes. |
| M3F — Strain | Implement every remaining consequence across all 72 cells and 22 Endgames, including actual recursive effects, prisoner escape escalation, mission obligations, deadlines and mandatory work completion. Scheduling a result is not applying it. |
| M3G — world/physical state | Implement actual movement/time, Frame occupancy/link/control, transport/custody, Harpy/Core consent, full NPC/Gorgon/Harpy/Director rules and prices/breach consequences. Original placement and some Gorgon operations exist; they do not supply these missing mechanics. |
| M3H — integration/acceptance | Native controls and durable owned responses for every remaining mechanic; complete source-backed golden traces, migration/recovery/privacy checks, independent rules review, then the agreed player tests and owner review. |

Implemented checkpoints include mission offers/rewards and discipline subsets;
owned Off-Duty/Observation workflows; selected Strain effects; actual world/cast
records; original body/Frame facts; Gorgon NPC attacks/Asset contests/Core exposure;
selected Requisitions and repairs; known-roll/shared-chain recovery; next-refusal
bonuses; private contraband; and Frame source classification. Their individual
work orders explain exact limits. Missing rules continue to fail closed.

Continue with the dependencies that support the remaining rules: actual Handler
character/playbook state, actor/persona ownership, physical/control state and
lifecycle effects, then complete the shared Plays and consuming playbook/Strain
branches. Preserve existing accepted M2 resources and histories. A profile label,
manual acknowledgement or generic narrative cannot replace a typed mechanic.

The frozen M2 release remains separate from development. Its source commit is
`88cd237e9dc32742d2ac89a4fd2e18a4df10fc24`, live schema `0011`. The absence of its
earlier execution process was detected during verification; the same hash-verified
release was restored with the existing policy/token binding, and Gateway readiness
plus 13 guild commands were confirmed. No M3 migration or gameplay deployment was
performed. Continuous hosting remains separate operational work.

Ancillary playbooks stay deferred and disabled. AI and M4 onward stay outside M3.
Future ambiguities use the owner's delegated recommendations and the central
adjustable rulings register; they do not waive source coverage or player consent.
