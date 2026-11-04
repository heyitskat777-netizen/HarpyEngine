# M3 initial source audit and implementation checkpoint

Status: IN_PROGRESS / RULES_SUBSET. This is not a complete branch audit or an
independent rules certification. M3 is not complete.

The supplied rulebook has 205 PDF pages; its patch notes identify the 2.0 rewrite
and list a latest update of 2026-09-01. The official sheets have 56 PDF pages.
Verified anchors use actual PDF pages and printed pages separately. Source
fingerprints/extracted working text remain under ignored private `var/source-audit/`;
no PDF, full book text, real campaign state or private engine is included in Git.

`rules/registry.json` inventories 473 named-source/table entries. They are not 473
implemented Plays. There are 72 distinct Strain cells (three tracks × two severities
× six die results × two columns) and 22 endgame slots, including distinct duplicate
advancement slots. Nested branches, options, source interactions and sheet/book
comparisons still need further audit. Seven M2 entries retain the honest `subset`
implementation marker; no entry has independent verification.

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
| Absent Ace bonus | Awaiting owner decision | Book PDF 16 / printed 14 does not state whether the separate Ace bonus requires participation |

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
  waive pending work. The absent Ace branch has no assumed policy while awaiting
  the owner ruling. Transactional persistence, frame-trigger reactions, mechanical
  Punishment resolution and Discord integration are still pending.

The new rules tests are synthetic. They are useful implementation evidence, not
finished M3 case acceptance. Required source/fixture matrices and all remaining
M3A–M3H work remain in the work order and acceptance plan.
