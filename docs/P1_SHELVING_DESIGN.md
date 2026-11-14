# Player shelving: intake implemented, activation blocked

## Requested outcome and current boundary

The owner requests GM-activated temporary player shelving, individually player-requestable, so cohorts can continue safely during absence. The intended effect is availability only, not a choice, refusal, consent, ownership change, NPC proxy, waived cost, or completed obligation.

**This increment is intake infrastructure, not the shelving mechanic. No player is frozen and no cohort is unblocked.** `/shelving request` records an individual request; the current configured human facilitator can propose shelving for a player or decline a request. The original player can withdraw it. `/shelving inbox` reconstructs pending requests after restart. Intake screens state the limitation. Activation fails closed with `SHELVING_UNAVAILABLE`; there is no activate button, active state, resume operation, or silently weakened scene gate.

Requests use existing private append-only campaign events and command idempotency. Each record preserves the original actor/incarnation, owner, initiating human, whether the player actually requested it, creation game revision, record revision, and GM configuration event when applicable. Reconfiguration immediately changes review authority. GM proposals do not claim player consent. No free-text absence or safety reason is collected or published. No new notice delivery or public disclosure is introduced. Normal membership and private owner/current-facilitator access apply. These are operational records, not gameplay events.

## Verified architectural blockers

1. `services/m3_easy_target.py::_finish` requires both no pending choices and no incomplete `Reaction`. Marking a choice complete, setting `completed_event`, or pretending the actor declined would falsify actual play. A separate parked state and suspended required-work relationship are needed.
2. `services/m2_game.py::pending_actions` counts unfinished actions; source recovery depends on the exact original scene and cast. Releasing a lock alone lets another scene invalidate the pending source. A durable original-scene recovery plan must precede lock release.
3. Canonical personal effects are not confined to `GameState.sheets`. Bonds, obligations, placements, world records, facts, archives, custody, lifecycle hooks and cross-actor outcomes can mutate an absent actor indirectly. A sheet comparison is not a whole-player freeze.
4. Choices, required work, action rows, receipts, locks and delivery are also stored outside `GameState`. A guard only in `GameService.event` misses SQL-only progression. A guard only in authorization misses indirect effects by other players or workers.
5. `GameService.event` runs lifecycle preparation after initial inputs, including indirect consequences. Guarding only the pre-hook proposed state would miss final effects. Some services persist side effects before canonical state; protection must cover the whole transaction and rollback.

## Proposed next implementation boundary

Freeze one original actor/incarnation, not a Discord account's future replacement. A distinct durable availability record should have requested/active/resume-review/resumed or declined/withdrawn states, monotonic revision, current authorized GM and configuration event, source request identity if any, and explicit activation/resumption events. Requests alone must never change availability. Preserve saved resources, identity, pending decisions, obligations and ownership; do not restore an old full-campaign snapshot on rejoin because it would erase others' intervening work.

Before enabling activation, inventory each supported cohort's actual action/choice/required-work/receipt/state records. Establish actor and source ownership for protected records. Introduce a transaction-scoped guard shared by all mutation paths (services, delivery completion and recovery), comparing canonical state **after** hooks and dependent SQL writes. Unknown/unclassified changes touching protected or shared state must fail closed, not rely on guessed actor IDs inside arbitrary facts. Do not infer ownership via generic string matching. Add explicit typed projection adapters per supported domain. The narrow first supported slice should be original NPC Easy Target use with preserved original cohort obligations; unsupported sessions remain blocked.

Parking is distinct from completing or aborting. Keep exact action IDs, reaction IDs, original cast/scene, choices, rolls, resource reservations, consent gates and durable source links. Add an explicit parked-source lifecycle and scene-lock owner transfer/recovery contract. Only prove an action parkable when the remaining work is wholly deferred to shelved actors and its active participants can resolve independently. Never globally filter `pending()` or teach `ChoiceEngine.finish` that absence is completion.

Existing native NPC cohort use permits an original NPC to finish without a nominee accepting. It does not authorize deleting the nominee's outstanding work or auto-recording a missed acknowledgment. On rejoin after the original use ended, retain the original player's normal missed acknowledgment; do not retroactively enroll them in a completed use. If the source remains live, revalidate exact original identity, scene/cast and source dependencies before presenting their own remaining choices. Stale buttons, delivery callbacks and old requests must reject for an active shelf and may not assume a newer incarnation is the original actor.

GM resumption is audited and reversible as availability, not automatic fictional catch-up. If source revalidation fails, stay shelved/resume-review and report the precise pending decision. Never rewrite the original outcome or automatically apply costs/consequences. OOC safety pause, private saved readback and shelving intake/review remain reachable; a safety pause is not a substitute for per-player shelving.

## Acceptance before claiming safe cohort progression

- Real original NPC use, shelved individual nominee, others finish, original choices and obligations unchanged; rejoin exposes original missed acknowledgment without reroll, fresh consent or retroactive participation.
- Direct player action and indirect other-player/worker change against protected personal state roll back **all** state, SQL records, events, resource spending and delivery staging.
- Unsupported cross-actor/shared changes explicitly block instead of silently bypassing the shelf.
- Original actor replacement, stale request/control and current-GM replacement retain exact authority and provenance.
- Restart, duplicate interaction and interrupted resume preserve original work and single receipts.
- Private absence information never leaks through status, generic ledger or notice paths.
- Explicit evidence for supported slices; no global freeze or all-rule safety claim without coverage.

Bot remains off. No deploy, merge, remote publication or private-engine mutation is included.

## Intake review corrections

A player's explicit request after a GM proposal appends a new revision recording
that player's request, while retaining the proposal's initiating GM and configuration.
Deduplication uses the exact original actor, so a replacement incarnation receives
a distinct request. Relevant current-GM and owner authorization runs before cached
interaction replay; saved outcomes cannot preserve revoked facilitator access.

## Pilot intake source validation (2026-11-10)

Pilot requests now resolve the original identity through the existing canonical
profile-snapshot/career proof before creation, promotion or cached replay. Newly
created requests preserve that proof privately. A changed character ID in an
otherwise unchanged sheet is not a replacement source. A request-key replay for
a different current incarnation is rejected; the old pending request remains
privately readable and withdrawable without transferring it to the newcomer.
Target membership is rechecked on replay as well as initial submission.

This repair authenticates Pilot intake identity only. Handler intake retains its
existing current-body contract. It supplies no availability generation, complete
actor incidence, resource ownership, drain or journal dispatch authority.
Activation is still unavailable and no existing obligation is completed.
