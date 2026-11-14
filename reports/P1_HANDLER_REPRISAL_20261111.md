# P1: actual Handler Feedback reprisal

Status: isolated implementation; worker-authored gameplay checks **NOT RUN**.
Baseline: `harpyengine-p1-princess-disobey-integrated-20261111`.
Bot OFF; RULES_SUBSET; no deploy, merge, publication, model calls, private-engine
writes, full regression, independent review or player-acceptance claim.

## Source and bounded behavior

Feedback Loop is rulebook PDF84 / printed82, `frame.ankou.feedback-loop`.
Its tear branch requires removal of an actual Asset, five actual Heat and an
actual Play against the selected scene person. It does not require Flirt.
Existing native Engage already accepts a genuinely cast Handler opponent. This
adapter reuses that real Play for Handler reprisals instead of inventing Handler
Flirt resources or borrowing a same-account Pilot/NPC. Existing Pilot/NPC Flirt
adapters are unchanged. This is finite adapter coverage, not permission to call
any arbitrary Play or represent every legal reprisal.

- Native final-mark Feedback and standalone Relay/Obsession Feedback expose
  Handler Engage using the exact original recipient and original actor.
- Before any loss, validate current Handler body, original actual cast/controllers,
  living present actors, source adjudicator and a surviving usable Engage Asset.
  Revalidate at child entry. Existing physical tear, stored/linked resource,
  mandatory-loss and original source gates remain.
- Real mark/Heat commitment stays held without a receipt. Tear removes only the
  actual selected Asset and grants the existing five-Heat source. The owner
  confirms the actual Engage; the final-mark native prompt explicitly states the
  existing all-current-Heat expenditure. Standalone entry retains its actual
  Heat controls and fixed target.
- Real Engage generates its own receipt, human-owned maneuver choices, damage
  and required work. No fabricated target resources, consent or result. Wait for
  actual required damage work before completing this Feedback source.
- Engage finishes after its canonical response event. Final-mark reprise closure
  therefore uses a distinct `m3.ankou_reprisal_completed` event referencing the
  actual source response/author and child. This durably reopens the held original
  Play with its original commitment. Standalone closure uses the existing real
  `m3.ankou_child_completed` sequence event and permission-restoration workflow.
- Private owner/recipient read boundaries, idempotent receipts and actual original
  parent resources remain in place. No `m2_game.py` changes or schema migration.

## Authored root minimums

1. `tests/rules/test_ankou_handler_reprisal.py::test_native_handler_feedback_tear_engage_and_original_roll`
   Native tear and actual Handler Engage, no usable-Asset guard, rejected Handler
   Flirt, private read scope, real mid maneuvers, five-Heat child receipt, durable
   Feedback proof, original one-Heat parent resumption and once-only receipts.
2. `tests/rules/test_ankou_handler_reprisal.py::test_native_relay_handler_reprisal_keeps_real_high_damage_and_completes_source`
   Actual Handler-only Relay source, native tear and fixed-target Engage, real
   high-result used-Asset damage, sequence completion and source-pause restoration.

Existing Handler purpose/refusal/Bond tests retain their ordinary checks; their
obsolete unsupported-tear projection assertion is replaced with supported Engage
availability. Existing normal cases are **not rerun** here. Other source adapters,
all final candidate regression/static/migration/privacy/restore gates and actual
independent/player review remain pending. No whole-Frame completion claimed.

## Static evidence

- Python AST parsing: all eight changed Python files passed.
- Existing installed Ruff: format and changed-path check passed for eight Python
  files. A later native cost-caption-only edit was rechecked on that changed file.
- Existing installed Mypy `--follow-imports=silent`: six changed source files
  passed. The final cost-caption-only file was checked again after its edit.
- No pytest, collection, gameplay test, broad compatibility sweep or new package
  installation was run by this worker. Root owns the minimum runtime checks.

## Review repair: single canonical sequence completion

Independent review identified a real duplicate-completion risk: Engage's
post-event synchronizer closes standalone Feedback using freshly loaded canon,
then the later `GameService.respond` hook can invoke the same consumer with its
pre-synchronize GameState. The shared action is already marked complete, so the
old in-memory step could otherwise generate a second completion and overwrite
newer state.

The standalone sequence completion consumer now reloads canonical state for its
explicit `feedback_work` source before any completion check or write. Both entry
points see the same saved completion and repeated calls return without a second
event. Existing task consumers and the necessary post-event durable path remain.
No `m2_game.py` change was needed.

The existing native Relay test now asserts exactly one source-specific
`m3.ankou_child_completed` event, the identical event on the step, sequence and
resolved work record, and byte-identical canonical state/work after replaying the
real completion with an intentionally stale pre-roll snapshot. That stale snapshot
has the old Heat and lacks the actual maneuvers/damage, so the equality assertion
specifically guards against overwriting those effects.

Changed-file Ruff and scoped Mypy passed after this repair. Tests remain authored
NOT RUN by this worker. Parent reported a disconnected executor during its prior
attempt, with outcome uncertain and no verified pytest result; this packet does
not claim those tests passed or authorize repeating an unresolved process.

## Root minimum and scoped fixture repair

Root reported the v2 two-node minimum as **1 passed, 1 failed in 5.63s**. The
final-mark Handler reprisal node passed. The Relay node stopped at the actual
Handler CastService join with `M3_REVIEW_PENDING` because the source fixture
approved plays/economy but not CastService's required world subsystem.

Only that Relay test's synthetic release approval now adds `world`, retaining the
existing synthetic registry/digest and real source operations. This matches the
established Relay/NPC fixture pattern. No production access guard, source proof,
Handler cast operation or gameplay implementation changed. Changed-test AST/Ruff
passed. Worker pytest remains NOT RUN; root should rerun only the failed Relay
node, not the already passing final-mark node.
