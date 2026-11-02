# Official GIRL FRAME Rules Port: Source, Scope, and Test Coverage

**Rule authority:** The supplied official `GIRL_FRAME_rulebook.pdf` and `GIRL_FRAME_official_sheets.pdf`. **Not** the experimental GM Skill or a summarized test transcript. PDF page references below are viewer PDF pages (1-based); the printed in-book number may differ by three. Read the exact printed Play before implementing.

**Source provenance:** The published game defines the Handler and Girls as separate roles, is deliberately Conversation-led, and generally uses 2d6+spent Heat with 8–10 / 11+ / 7− outcomes. Exact exceptions, source text, target priority and result choices must be reviewed individually. We do not reproduce the complete copyrighted Play text here.

## Ruleset registry contract

Every production Play entry must specify `play_id`, `scope`, `rulebook_pdf_page`, `rulebook_printed_page`, `trigger`, `actor_type`, `pre_roll_sources`, `roll_kind`, `allowed_modifiers`, `tier_options`, `choice_ownership`, `target_policy`, `post_roll_effects`, `mandatory_followups`, `handler_or_gm_intervention`, and `test_fixture_ids`. It remains `UNIMPLEMENTED` until verified by independent rules audit and at least one positive/negative/each-tier test. `UNSUPPORTED_RULE` must fail closed; no LLM-created substitute.

## Coverage matrix for implementation order

| Subsystem / Play | Published reference (printed) | Required tests / special concern | Target |
|---|---|---|---|
| Heat, Identities, Tags, Bonds | Core Rules pp. 8–11 | 5+ Heat mandatory spend, pre-roll Identity mark, post-roll Tag limited, mutual Bonds | M2 |
| Status and Receive Orders | Core pp. 12; basic Girl pp. 19–21 | exactly one Ace and Dog; adjacent Status displacement; a higher-Status order must be recognized | M2 |
| Keep Your Head | Basic Girl p. 19 | three tiers, exact selections, consequence/GM ruling | M2 first |
| Check Sensors | Frame p. 24 | target questions and answer counts by tier | M2 first |
| Engage the Enemy | Frame p. 23 | Asset legal options, 11+ or 7− damage | M2 first |
| Disobey Orders | Girl p. 21 | witnessed direct superior order and 7− programming halt | M2 after Receive Orders |
| Flirt | Girl p. 20 | human target question/response; 11+ extra choices; 7− Bond weakening, no scripted consent | M2 after pending choice workflow |
| Put Someone Beneath You | Girl p. 20 | player-vs-player option ownership and consequences | M3 |
| All-Out Assault | Frame p. 23 | 11+ Handler choices, 7− enemy damage/Handler Play | M3 |
| Go for the Core | Frame p. 24 | Core exposed, undamaged Asset modifier, lethality/defeat interaction | M3 |
| Dive Deep | Frame p. 22 | Void tradeoffs, 11+ Handler choice, Status reduction | M3 |
| Go Off-Duty | Misc p. 25 | Status-modified roll, mandatory harsh scene, real offscreen punishment, End-of-duty recovery | M3 |
| Void Observation | Misc p. 25 | alternative to Go Off-Duty, Status reduction and two-party options | M3 |
| Defeat | Misc p. 27 | Girl Assets modifier, 7− catastrophic choices, 11+ Handler rescues | M3 |
| Girl Playbooks | Girl Playbooks pp. 28–57 | all base types, printed Play exceptions, exact Sex Play discretion; use safety gates | M3 |
| Frame Playbooks | Frame Playbooks pp. 58–89 | Frame-specific Assets, permission triggers, resource effects | M3 |
| Handler Plays / Handler Playbooks | Handler pp. 113–139 | diceless Plays, Handler Tags, Frantic etc. | M3/M6 |
| Missions and Gorgon Movements | Quadrant Twelve pp. 119–121 | arrival, participant set, world map/state, compulsory mission-end rewards/Punishments | M3 |
| Void, Rebellion and Budget Strain | Strain pp. 140–150 | all Low/High d6 rows, both event columns, recursive 6s/endgames, mandatory trigger effects | M3, critical |
| Gorgons, Harpies, NPC/Director | p. 159 onward | autonomy, diverse Gorgon classifications, Director price due, NPC playbooks | M3/M5 |
| Player-facing Requisitions/Punishments | Core pp. 14–16 | choices owned by player/Handler, exact effects, Dog at mission end | M3 |

**Note:** Source references above identify rule families to inspect, not a guarantee that every title starts on exactly that printed page. Codex must verify each PDF page and record its verified source location in the registry. This package deliberately does not assign exact outcome text beyond test necessities.

## High-priority known v1.3.9 regressions to eliminate

**RUL-001 Status exchange:** T199 success must actually swap Wing→Ace and Ace→Wing, and adjust subsequent modifiers/permissions. One-use Oldgen maxim created and consumed exactly once.

**RUL-002 High Budget recursive event:** A High Budget roll of 6 in the second column may require **two extra Budget table rolls** or an Endgame per printed conditions; cannot remain indefinitely pending as a generic ledger debt.

**RUL-003 Low Rebellion escape:** On the relevant prisoner-escape result, failure to address the escape must actually increase Rebellion Strain at the prescribed trigger.

**RUL-004 Flirt 11+:** All printed 11+ consequences/options must be represented; no invented Tag may be substituted for an unrecorded selection; the target human owns their answer.

**RUL-005 Go Off-Duty 7− and Princess Show Dog:** Stage required harsh scene, and capture both extra Princess selections and relevant NPC Bond effects.

**RUL-006 Director price:** A binding price with an in-world due date cannot expire harmlessly. Resolve, breach with recorded retaliation, or place valid dispute requiring facilitator; do not silently waive.

**RUL-007 Harpy refusal and continuity:** If the Harpy escaped and is free, GM cannot narrate arrival at K-17 unless an actual later event changed location/custody. Differentiate medical consent from Core conversion consent.

**RUL-008 Player authority:** Nobody, including an AI Handler, supplies another human Girl's Flirt answer, Status-dependent choice, acceptance, voluntary words or private reveal.

**RUL-009 Mandatory Dog punishment:** Applies at end of mission even if Dog not a participant; offline resolution policy must preserve real player's choice and not falsely apply it off-screen.

**RUL-010 No unprinted binary rescue quotas:** GM may present motivations and factual constraints but cannot impose hidden roll quota or predetermined target consent that contradicts Conversation.

## Rules audit files Codex must produce per subsystem

- `rules/registry.json` with one entry per implemented printed Play, exact source anchor and verification status.
- `tests/rules/test_<play>.py` with happy-path, each tier, illegal input, owner permissions, replay/idempotency, and late choice.
- `docs/RULE_COVERAGE_REPORT.md` with implemented, verified, pending and unsupported entries. “Complete” only if 100% of agreed official rules and edge branches are covered and independently tested.
- `tests/golden/*` containing **synthetic** event traces, not real user campaign or old simulated Turns 195–294 imported as canon.

## Non-rules mechanics

Narrative Personal Stakes are optional zero-bonus witness records. The proposed *Stand Together* new rolled Play and numeric Relationship Pressure clock are NOT activated. Any other house rule requires explicit campaign-level consent, its own version, and tests. Never silently promote a house rule into official rules.
