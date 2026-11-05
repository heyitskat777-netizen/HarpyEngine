# M3 initial source audit and implementation checkpoint

Status: IN_PROGRESS / RULES_SUBSET. This is not a complete branch audit or an
independent rules certification. M3 is not complete.

Latest focused development records 240 adjustable clarifications and 135 subset /
338 unimplemented entries, including the 37 deferred Ancillary entries. No entry
has independent verification. New evidence covers bounded Alpha/Guard/NPC Orders,
normal JANUS Storage and selected Budget lifecycles; three Budget source contracts
were added. Remaining playbooks, table branches and world interactions still
prevent completion. The 2,200-test full regression below covers earlier source.
See current [acceptance evidence](../reports/M3_ACCEPTANCE.md); older counts and
Storage acquisition limits below are historical.

The supplied rulebook has 205 PDF pages; its patch notes identify the 2.0 rewrite
and list a latest update of 2026-09-01. The official sheets have 56 PDF pages.
Verified anchors use actual PDF pages and printed pages separately. Source
fingerprints/extracted working text remain under ignored private `var/source-audit/`;
no PDF, full book text, real campaign state or private engine is included in Git.

`rules/registry.json` inventories 473 named-source/table entries. They are not 473
implemented Plays. There are 72 distinct Strain cells (three tracks × two severities
× six die results × two columns) and 22 endgame slots, including distinct duplicate
advancement slots. Nested branches, options, source interactions and sheet/book
comparisons still need further audit. Current implementation counts come from
`tools/check_rules_registry.py`; partial implementations retain the `subset`
marker and no entry has independent verification.

The current frozen bounded candidate updates contracts/evidence for **35 entries**
and records **166 adjustable campaign clarifications**. Current inventory state is
**104 subset entries / 369 unimplemented entries**, including 37 deferred Ancillary
entries. All 436 required core entries still await independent review. This
corrects stale per-feature inventory metadata; these unequal source entries are
not a progress percentage. The new full regression passes **2,200 tests**; the 1,983-test build remains
historical evidence. See
[the current implementation map](M3_PARALLEL_WORK.md) and
[the remaining-work inventory](M3_REMAINING_WORK.md).

## Current module scope

Per owner instruction, the eight ancillary playbooks are an optional `ancillary`
module, disabled by default and deferred. There are 436 current core inventory
entries and 37 deferred entries. Deferred entries include their shared exceptions,
Rebellion's ancillary lesson, Captured's ancillary conversion, and Timeskip's
ancillary introduction. Disabling the module never substitutes another consequence
or permits rerolling. Even a future configuration flag cannot execute unimplemented
or unreviewed optional rules. Coverage reports identify their enabled module scope.

## Recorded campaign rulings

| Ruling | Decision | Source issue |
|---|---|---|
| Void Observation reprogramming fallback | If the starting set has no Malfunctioning, the player selects an ordinary starting slot for a retained current Identity; preserve protected/extra Identities | Book PDF 28 / printed 26; five base Girl playbooks lack that slot |
| Unpriced standard Requisitions | Creature Comforts, Privacy and Asset Installment each cost 1 Permission | Book PDF 16 / printed 14; sheets PDF 40 omit these prices |
| Budget shortage extra repairs | The current Handler explicitly sets the price for each extra repair; no default cost | Book PDF 150 / printed 148; sheets PDF 43 allow paid repairs without a price |
| Absent Ace bonus | Owner approved granting it to the current Ace even when absent | Book PDF 16 / printed 14 does not state whether the separate Ace bonus requires participation |
| Unspecified Punishment details | The inflictor chooses details; explicit printed ownership overrides this default | Book PDF 17–18 / printed 15–16 |
| Mission failure and Dog overlap | One actual Punishment covers both causes for the same Girl in the same mission; preserve both cause records | Book PDF 16–17 / printed 14–15 |
| Sedation with fewer than two Identities | Mark all remaining Identities and set Heat to zero; preserve explicit Paired Identity effects | Book PDF 17 / printed 15 omits a fallback |
| Princess Permission timing | Promote Status first; if now Ace, grant the Princess Permission, then determine normal mission/Ace rewards separately | Book PDF 32 / printed 30; owner-approved interpretation |
| Compulsory Frame package | The current Handler specifies each package; the player must choose a different official Frame playbook | Book PDF 71 / printed 69 and PDF 29 / printed 27; owner decision |
| Compulsory Frame price | No Permission charge; optional paid Frame Swap remains separate | Book PDF 16, 29 and 71; owner decision |

Previously approved starting conditions, JANUS-B alias and Intense ±2 modifier
remain separate existing rulings. No new ruling is silently applied to live policy.

## Implemented offline foundations

- A strict typed registry checks source bounds, unique IDs, dependencies, truthful
  implementation/review provenance and module availability. A heading or test alone
  cannot earn independent certification. `python tools/check_rules_registry.py`
  reports the actual incomplete coverage.
- Pure Asset cap/damage/corruption/recovery operations clone their inputs and emit
  required Defeat/Helpless/Void-threshold follow-ups. They do not discard mandatory
  reactions or claim complete playbook interaction coverage. All-Asset normal
  recovery and selected shortage repair quotas remain distinct; Sedation locks
  prevent an illegal off-duty Identity unmark.
- Reprogramming label choices implement the approved fallback and preserve
  protected extras. Applying reset marks and all associated effects remains later
  resolver work; this function does not pretend to finish a reprogramming action.
- Pure Permission charges distinguish printed prices, owner rulings and a
  current-Handler repair quote. Stale revision/owner/Handler/price contexts fail.
  Services still need to authorize/persist quotes, owner confirmation and grants.
- Source-based decision contracts cover remaining shared Plays across all three
  tiers, with exact ownership/counts, conditional punishment authority, fixed
  consequences and pre-roll requirements. Every plan explicitly requires subsequent
  mechanical application; no new Play is exposed as resolved in the live bot.
- The pure mission lifecycle requires actual invited-player responses, an active
  roster and current Handler. It plans base/explicit Ace rewards and retains
  failure/Dog consequences, including an absent Dog. Mission completion cannot
  waive pending work. The approved campaign policy grants the current Ace its
  separate bonus even when absent.
- Transactional mission persistence now uses private projections and append-only
  histories. Mission rewards share a transaction with canonical Pilot state and
  required consequences. Duplicate/concurrent submissions cannot grant twice.
  Native private mission controls and the requests inbox enforce actor ownership,
  revision checks and explicit responses. An absent Dog sees its required work
  without receiving the private mission objective.
- Known Princess and DoctorDoctor mission-end reactions block rewards until their
  source-specific work is resolved. Typed handlers now apply a standards review
  and one Obsolescence mark for an actual Cadre mission failure. Their private
  native controls are in `/mission reactions` and the requests inbox. Princess
  grants its approved post-promotion benefit before the final normal reward
  snapshot. DoctorDoctor fills at eight boxes, marks the Frame scrapped and queues
  owner-controlled replacement; neither rewards nor new missions/Plays bypass it.
  Other Obsolescence triggers currently have pure-domain coverage only; their
  production triggering Plays/events still need implementation. Migration `0012` is tested
  on populated synthetic `0011` data; no live migration or M3 activation occurred.

The new discipline subsystem applies eleven printed types plus Passing Responsibility
as a transfer of pending work. It records one application against both failure/Dog
causes, never twice. Delegated Girls must obtain the current Handler's consultation
on the exact Moderate proposal; changed game state or choices invalidate approval.
Requests and `/mission discipline` provide native owner-bound controls. Only the
assigned inflictor receives the sheet labels necessary for its choices, without
notes, descriptions or review snapshots. Explicit Paired Heat sharing stays owned
by the affected player and commits once after Sedation. Off-duty Sedation locks
are retained by the pure recovery reducer; the mission service applies pre-Off-Duty
discipline only. Handler Heat from an Intense Bond is tracked in canonical state.

Revoked Privileges and all four Severe types remain unavailable. Strict Regulations
now has private typed imposition, explicit disclosure choice, exact Moderate
consultation, informed Handler breach review and separate source-bound discipline
causes. Current-context and future-period timing remain distinct through recovery.
Ankou and Void-context work remain blocking until their typed resolvers
exist; no acknowledgment waives them. The last-Girl-Asset Beating resolver now
requires the current assigned Handler's factual Frame-context review: apply
Helplessness against the inflictor outside a Frame, or record why that printed
condition does not apply inside one. The review is typed and auditable, not a
waiver. The Libido Inhibitor condition is persisted;
future Sex Plays must enforce it before release. Remaining playbook interactions
and noncanonical initial NPC Bond migration still need audit and implementation.

The owner approved Sedation's small-set fallback; zero/one-Identity paths now
apply only after confirmation and create no synthetic Identity. Compulsory Frame
replacement now has approved policies: Handler-defined package, different official
playbook and no Permission charge. The DoctorDoctor-scrapping path applies an
exact player-confirmed package, separately owned Court consent and typed Frame
setup, while preserving Girl state. It binds the original Frame/character and
updates the canonical Frame, public profile, immutable snapshot and cosmetic sync
intent atomically. Changed quotes/state invalidate old forms. All package text has
paged private review. Defeat's destroyed-Frame trigger is still unimplemented;
additional unlocks require registry availability and further Void work remains
blocking. Core/Court state here is baseline setup, not complete World/AM mechanics.
The workflow and acceptance requirements are in `work_orders/M3_FRAME_REPLACEMENT.md`.
This remains a partial implementation and branch audit.

DoctorDoctor credit recipients and Off-Duty Sedation duration have since been
resolved under the owner's delegated recommendations. Their exact decisions,
alternatives and implementation notes are in `CAMPAIGN_RULINGS.md`.

The new rules tests are synthetic. They are useful implementation evidence, not
finished M3 case acceptance. Required source/fixture matrices and all remaining
M3A–M3H work remain in the work order and acceptance plan.


## Observation and separately played roles checkpoint

Actual Observation substitution, locked Status/Void roll, final Tag-adjusted tier,
owned selections and nested effects now have offline engine/service/native tests.
Real NPC role invitations and a separate appearance response preserve human control;
a non-Pilot Director can participate without an invented character sheet. Its
printed Handler/Girl context creates separate blocking work, rather than silently
allowing ordinary Handler authority. Full Director rules/prices, automatic world
triggers/reprimands, future-period ordering and remaining battle/playbook/economy
interactions remain incomplete. See `work_orders/M3_OBSERVATION.md`; this is not
full M3 acceptance or a live gameplay release.


Director context now has an actual Handler presence review, two owned ordinary
starting Identities, the printed zero-Heat start and separately controlled
departures. No Pilot sheet or Cadre Status is fabricated. Overlapping Directors
share one episode; the final departure grants no recovery. Actual completed scene
cast/attestations can establish the Handler was absent. Own scene confirmations
have a narrow path separate from Handler powers. Shared Girl Play integration,
Director Handler Plays, prices/phone calls and broader cast/world interactions
remain incomplete. The global separate-Director-player rule is a campaign
recommendation: the explicit printed requirement is High Budget 1/1 (PDF 151),
while generic NPC control is broader. See the central rulings and M3_DIRECTOR.md.


Actual actor references and source-proven scene casting now distinguish human
controllers from their fictional roles. Saved Pilot Plays bind character
incarnations, including legacy generations proved by immutable original state.
The Handler's facilitator role does not claim its fictional presence. Private NPC
information and unmodeled resources are not transferred to another role of the
same human. The mixed-role Play/resource consumers remain unimplemented and
fail closed. See `work_orders/M3_ACTORS.md`; this is a partial foundation.


Strict Regulations uses book PDF 17 / printed p.15, with Moderate consultation at
PDF 18 / printed p.16. Its rule is separate from public/Pilot-sheet resources and
bound to the actual character incarnation, inflictor and informed Handler. Hidden
rules stay out of the subject's consultation view and unrelated projections. The
Handler explicitly records a real breach and its due context; no chat is ingested
or judged automatically. Each breach creates a separate actual discipline cause,
which cannot merge with the mission failure/Dog overlap. Future-period debt does
not block current-period recovery but becomes required work on the next actual
period. A synthetic two-period test applies the further Punishment once, with
separate owned on-screen attestations. Handler knowledge-transfer, career archives,
remaining Punishments, full economy/playbook and other M3 work still remain.


Low Budget 4/2 (PDF 150 / printed p.148) now has actual Strain-source, next-dispatch,
mission-end and recovery-period provenance. Its current-period recovery remains
unchanged when the source first arms; the following actual recovery limits free
repairs to one damaged Asset per family. Native owner selectors preserve remaining
damage. Optional extra repairs use exact current-Handler Permission quotes and
separate player confirmation, with no default price or automatic spending. Quote
revisions, character/Frame incarnations, safety, affordability, chat restoration,
rollback/replay and actual period closure are covered offline. Other Requisitions,
Casualty body parts and remaining playbook/world/economy interactions remain
unfinished. See `work_orders/M3_SHORTAGE_REPAIRS.md` and the central timing ruling.


Low Budget 3/2 (PDF 150 / printed p.148) now draws a source-bound actual Cadre
recipient with an OS uniform primitive and records a separate −2 pre-roll recovery
modifier. It retains original character/population provenance privately, consumes
once at the real roll and survives known-roll recovery without redrawing. Base
Status/Void Assets and later Tag/Bond modifiers remain separate in receipts and
period history. Observation uses the recorded delegated interpretation. Native
controls never let the Handler select the random recipient. Other temporary
modifiers and remaining Strain/playbook/world/economy rules remain unfinished.
See `work_orders/M3_SUPPLY_LOSS.md` and the central ruling register.

WYVERN's Enormous exception is now enforced in actual activation, paid Asset
Installment, compulsory replacement packages and native selectors (book PDF 74 /
printed p.72; ordinary caps PDF 15 / printed p.13). Five ordinary Frame Assets
fit alongside Enormous; it cannot be selected for cap replacement. An actual
source marker, or proven original legacy identity, supplies the properties.
Naming a custom Asset Enormous grants no exception. Damage, repair and counting
surviving Assets for Defeat still include the actual intrinsic Asset. This audits
only that printed exception and the partial core cap operations; full WYVERN
Plays, special control/transport and further Asset interactions remain unfinished.


Low Budget 3/1 (PDF 150 / printed p.148) now records one or two actual scientific
Observation orders, with explicit per-Girl hiding decisions and distinct real
source events. It preserves original contexts and distinct causes under the logged
one-roll overlap interpretation. The actual Observation route, lowered Status,
owned consequences, scene and Frame review still gate recovery; resolving the
Strain source alone grants none of them. Two-cause settlement has a complete
synthetic owned scene/recovery trace. See `work_orders/M3_SCIENTIFIC_OBSERVATION.md`.

Low Rebellion 1/2 (book PDF 147 / printed p.145) now schedules a source-bound +2
for the actual next Cadre Girl refusal. Its original selected event, period,
resolved work and actual effect event are proved before dice. The Handler cannot
select a recipient. Reservation freezes pending sources; the first actual
committed roll consumes them, and a competing stale reservation stops before
RNG. Receipts distinguish Heat, this pre-roll adjustment and later Tag modifiers.
The delegated overlap ruling is logged centrally. Other actor-aware Disobey
Orders and Handler/career transition consumers remain unfinished.

Shared Pilot Plays under the approved M3 protocol now retain actual root/child
interruption evidence. Owned resume restores pending decisions after chat
restoration, with original dice, spending, answered choices and ownership.
Known descendant rolls cannot be discarded through a diceless parent. Old aborts
without evidence receive no invented recovery. Known actor/Off-Duty interruptions
also remain blocking after chat restoration. Native controls and private backup
preservation are checked; this is not complete M3H or full runtime certification.
Unrolled reservations do not block otherwise safe world changes. A source-proven
legacy metadata bind can enable recovery of a known roll without changing its
receipt, prior answers or mechanical resources.

Low Rebellion 2/2 (book PDF 147 / printed p.145) now has actual uniform source
selection and a private optional Girl Asset decision. Original source snapshots
prove the recipient/index; changing a current record cannot grant another human
private access. Known absent Girls cannot be moved or filtered out before the
draw. The owner confirms the actual finding or declines; normal Asset caps and
Void protection apply. Public sheet settings do not automatically expose this
Asset. Explicit sharing, private ledger/export projections, damage/recovery,
original-character proof, native controls, rollback/replay and backup preservation
are checked. This does not implement travel, career/control or every later means
of discovering a secret. See `work_orders/M3_CONTRABAND.md`.


Frame source classification now distinguishes nine actual playbook headings,
30 base rules, 52 playbook Requisitions and 13 Class Requisitions. Exact printed
Requisitions heading positions were checked on the mixed pages, including
Nanobot Injection as base and Borrowed Wings as acquired; Psych Strings is also
base. Book PDF 92–94 / printed pp.90–92 belongs to the three Classes, not Red
Queen. Those 13 canonical IDs retain their original IDs as historical aliases.
Project Ankou's heading was incorrectly a mechanic; The Prince was already a
playbook. The earlier hypothesis naming Prince was incorrect. Category/alias
validation and replacement-package heading rejection preserve that distinction.
This changes neither runtime implementation counts nor independent review. See
`work_orders/M3_FRAME_CLASSIFICATION.md`.
