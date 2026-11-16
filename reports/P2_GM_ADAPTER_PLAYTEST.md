# Structured GM adapter: offline playtest candidate

Subsequent work: [all-Play referral and review coverage](P2_ALL_PLAY_COVERAGE.md)
extends review routing and native verification. The five structured outcome
consumers and historical evidence below retain their original scope.

The adapter is ready for attempted **offline playtesting of five ordinary native
Plays**, with fixture or manually supplied GM judgments. This is the result of
implementation, a 40-case rerun, follow-up review/fixes and targeted adverse-input
checks. No real-model quality, autonomous live operation or all-Playbook support
is claimed. Activity UI integration remains deferred by owner direction.

Development starts from `f73a5da8fc6a6a6f7ce357fe70c5ae90fe85fc18` on
`codex/r285-integration-20261114`. The runnable audit records its source hashes in
`var/director-protocol-audit/summary.json`; final local verification also records
changed-file hashes in `var/gm-adapter-validation.json`. These ignored outputs
contain only disposable synthetic trial material. The source commit containing
this report identifies the delivered candidate. Frozen live runtime v0.1.4,
original planning files and database schema are unchanged; no deployment occurred.

## Implemented boundary

The engine proves the accepted declaration, current actor, original native dice
receipt, actual selected traits, pending choices and outcome provenance. The
configured facilitator supplies explicit stakes, individual demands and
evidence-bound prerequisite interpretations. The private provider packet includes
canonical campaign state and native records, source references, and the latest
100 scene inputs with an explicit omitted count.

`GMProvider.propose(GMPacket)` supplies contextual assessments and private
reasoning. The engine validates request identity, cited evidence, actual trait
polarity, demand coverage and consistency, unknown/blocked prerequisites, native
stage and an empty extra-effect set. It does not require the provider's words or
judgment to equal a keyword oracle. An unsupported mechanical or world command
has no consumer. The default provider requests Keep clarification rather than
pretending to understand arbitrary narration.

For Keep, only the original `handler_keep` choice controller can confirm the
proposal. That confirmation rechecks current consent, source, context and choice
inside the original native response transaction. Exact retries preserve the
original response and dice. This human mechanical role does not grant the
fictional Handler the private GM prompt or reasoning.

The other four Plays retain their native question/answer, maneuver/damage,
order/child and target-owned workflows. They are not collapsed into Keep's binary
goal test. Disobey verifies the real Receive Orders parent and superior order.
Unsupported nested/unusual Playbook consumers fail closed.

Participant readback uses fixed templates plus the existing native audience
projection. Provider prose, stakes, demand descriptions and raw GM context are
never copied into participant/Handler speech. Other owners' pending choice and
work details are suppressed. Each view distinguishes a confirmed proposal,
currentness, current viewer's confirmation permission, immediate action completion
and known remaining action/scene work.

## Repeated experiment and review

Commands:

```bash
.venv/bin/python tools/audit_director_rulings.py --protocol
.venv/bin/python tools/playtest_gm_adapter.py
```

The original 40 inputs and 36 narrative settings are retained. New explicit
facilitator frames and trait-relevance annotations are in
`tools/fixtures/director_gm_frames.json`; these feed a fixture provider, not a
language model. Expected verdict labels are still withheld from that provider.
Because a human authored these interpretations, the results demonstrate protocol
coverage and safe native integration, **not an improvement score for autonomous
GM reasoning**. The [historical v1 audit](P2_DIRECTOR_RULING_AUDIT.md) and its ten
poorly grounded judgments remain preserved.

| Observation | Final result |
|---|---:|
| Attempts / native rolls / immediate actions completed | 40 / 38 / 38 |
| Keep proposals matching annotated fixture expectations | 24 |
| Keep enough / not enough / clarification | 9 / 4 / 11 |
| Other-Play pending-choice adapters / complete adapters at first probe | 7 / 7 |
| Expected invalid requests blocked before RNG | 2 |
| Missing native/lineage adapters or unexpected runtime errors | 0 |
| Immediate actions retaining separate obligations | 3 |
| External model tokens / spending | 0 / 0 |

Sensors preserves its native 1/2/3 questions and original controller answers.
Engage preserves its maneuver selections and native damage. Disobey proves actual
order/parent lineage and required owner responses. Flirt retains the target's
private response and printed follow-up ownership. Handler context/public view
canaries, native roll replay and no-mutation-on-proposal assertions run in the
pack. Pilot, target and non-Keep controller inputs are explicit fixture scripts;
they are not generated GM decisions.

`disobey_barracks_mid`, `flirt_hallway_mid` and `flirt_canteen_high` finish their
immediate actions while retaining separate obligations. The candidate correctly
reports `fully_resolved=False`. Rechecking completion also exposed missing
scene-required-work accounting; the adapter now uses the latest append-only work
revision and keeps unresolved parent actions explicit. This flag describes known
action/scene work, not campaign-wide completion.

The manual console was exercised with a different, valid private calibration
assessment followed by original-controller confirmation, and with clarification
left pending. The latter exposed a console-only assumption that every native
participant view had a completed result. It now accepts the native pending/null
result without fabricating completion.

## Focused validation

The final synthetic trial uses existing observation, context, shadow, conversation,
native adjudication and database tests plus the new adapter checks:

```bash
.venv/bin/python tools/run_director_trial.py
.venv/bin/pytest -q tests/test_m2_game.py::test_keep_three_tiers_and_handler_ownership
```

The final integrated synthetic trial passes **53 cases, zero failures/errors/
skips** in 29.26 seconds. The three existing native Keep-tier/ownership cases also
pass in 2.79 seconds. Changed-source lint/format and types pass (11 Python files,
six typed source modules). Registry, original planning and publishable/manifest
checks pass with zero findings. Exact counts and changed-source hashes are
retained with the local JUnit/snapshot outputs; focused push CI covers the same
selected workflows plus the earlier bounded pre-live packet.
This is a focused validation packet, not a new full repository regression.

`tests/test_gm_adapter.py` covers valid alternate provider prose, private canaries,
wrong owner denial, exact replay without rerolling, wrong request/evidence/trait
polarity, omitted demands and unauthorized effects, unknown/blocked prerequisites,
source revision/GM authority, generation-time changes, transaction-time staleness,
withdrawn consent and latest scene-work completion/privacy. The tests use actual
native actions and owned choices. Source lint, formatting, applicable types,
runtime registry, original planning and publishable/manifest checks are required
for the delivery. No real Discord/model calls are part of these commands.

## Trying it before the UI exists

```bash
.venv/bin/python tools/playtest_gm_adapter.py --list
.venv/bin/python tools/playtest_gm_adapter.py --case precision_control_mid --interactive
```

The console exports a private synthetic request and an initially safe
clarification proposal under `var/gm-adapter-playtest/<case>/`. Edit the proposal
in another editor and press Enter. Keep its exact request ID. For a resolved Keep
proposal, assess every demand, cite goal/receipt/traits and any condition IDs, and
use actual selected traits/polarities. A minimal assessment entry is:

```json
{
  "demand_id": "demand-1",
  "sufficient": true,
  "evidence_ids": ["goal", "traits"],
  "traits": [{"trait": "in_control", "polarity": "are"}],
  "private_reason": "Control supports holding this calibration needle steady."
}
```

That is a facilitator judgment for this context, not a permanent trait-to-task
rule. An accepted enough/not_enough proposal still prompts for original offline
Handler-controller confirmation. Clarification or declined confirmation leaves
the native ruling pending. Each invocation removes its temporary database on
exit; the console is a single-attempt adapter exercise, not a persistent campaign.
Default mode rehearses all five Plays and writes readable HTML results.

For a custom synthetic goal, add `--goal TEXT --frame FILE` in interactive mode.
The JSON frame supplies `stakes`, distinct `demands` (`id`, `question`) and
`intent` (`established` or `needs_clarification`). Live data remains out of scope.

## Remaining work after this candidate

Attempt human offline playtesting to evaluate whether the framing/proposal/
confirmation flow is clear, fair and paced appropriately. Record genuine
misinterpretations rather than adding more fixture synonyms. A real provider will
need separately implemented transport, verified model support, usage limits and
data handling before any spending. Printed-rule/source review and human narrative
quality acceptance remain open.

General generated narration/Handler answers, broader Playbook/child consumers,
cross-scene continuity, autonomous world effects, real capture/retention, installed
workers and live publication remain unsupported. The later Activity should use
the [consolidated Python service handoff](../docs/P2_ENGINE_TRIAL_HANDOFF.md) to
build authenticated framing/review, original-owner confirmation, stale refresh
and participant projections. No UI repository handoff is needed to try this
offline candidate, and no connected Activity/HTTP layer is claimed.
