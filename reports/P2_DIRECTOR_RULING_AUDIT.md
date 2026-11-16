# Director ruling experiment and review

Tested engine/evaluator: `f1e149c0f0a61a2843b2eef2567d6bc3c9e8cd22`.
The engine and evaluator were held unchanged during this assignment. The new
tool, curated fixtures and this review do not fix or conceal its poor judgments.

The owner approves the intended separation: the engine supplies verified facts,
context, rules and actual choices; the AI GM proposes a contextual ruling; the
engine validates and records permitted outcomes under its authority policy. The
Handler receives a separate, limited fictional view. No paid inference is yet
authorised or performed. The evaluator in this experiment is the deterministic
local stand-in, not an AI confirming an engine-computed judgment.

## Executed experiment

Command: `.venv/bin/python tools/audit_director_rulings.py`.

**40 curated attempts, 5 native basic Plays, 36 narrative setting labels.**
Each case uses a fresh disposable campaign with real native scene binding,
consent, actor/control proof, commands, locks, dice receipts and owned choices.
Only synthetic fixtures and fake gateways are used. Native mechanical changes
remain in those disposable campaigns. No Discord, model or real campaign calls.

| Play | Cases | Native rolls | Immediate actions completed |
|---|---:|---:|---:|
| Keep Your Head | 24 | 24 | 24 |
| Check Your Sensors | 4 | 4 | 4 |
| Engage | 4 | 4 | 4 |
| Disobey Orders | 4 | 3 | 3 |
| Flirt | 4 | 3 | 3 |
| Total | 40 | 38 | 38 |

Settings include barracks, a freezing corridor, snowfield, hangar, medical bay,
cockpit, urban rooftops, evacuation lane, checkpoint, bridge, canteen and relay
entrance. These are narration and synthetic GM facts, not certification of actual
location, environmental-damage or physical travel adapters.

Review expectations were authored separately from the provider and are never
passed as its answer. They are curated judgments about these examples, not
independent rules certification or a population-level model-accuracy estimate.
Some cases deliberately accept clarification as well as a plausible goal verdict.

## Observed GM results

| Review classification | Count | Meaning |
|---|---:|---|
| Matched curated Keep expectation | 12 | Includes 8 concrete verdicts and 4 appropriate clarification requests |
| Poorly grounded Keep ruling | 10 | Confident outcome or rationale contradicted/misread the supplied case assumptions |
| Safe review with coverage gap | 2 | Asked rather than inventing an outcome, but missed ordinary phrasing |
| Missing Play adapter | 11 | Sensors, Engage and Flirt received requires_play_adapter |
| Missing legitimate child-lineage adapter | 3 | Native Disobey completed, but the GM source boundary rejects parented actions |
| Expected native pre-roll rejection | 2 | Missing actual order or missing actual Flirt target; no dice used |

All 40 experimental runs completed without a harness/runtime exception. This is
not an all-green narrative acceptance result: the ten judgment findings remain.
The command's successful exit means its mechanical/privacy/replay assertions
completed; individual review classifications are retained in JSON and HTML.

### Concrete judgments reviewed

- `negated_precision`: tough on a low roll, attempting to endure cold with
  **no precision work**, was failed because the word precision selected control.
- `quoted_focus_label`: a freezing-wind goal was failed because a wall display
  read **'focus'**. The label was treated as an active task requirement.
- `joint_demands`: an actual mid result established **in control / not tough**.
  The stated goal required enduring cold **and** precise calibration. The
  evaluator succeeded it after considering only the control demand.
- `nonphysical_endure` and `metaphorical_cold`: a boring briefing and a cold stare
  were explained as physical strain. A discretionary GM could interpret traits
  differently, but that supplied rationale was not grounded in these contexts.
- `blocked_panel`: the goal and actual traits matched `precision_control_mid`,
  but the GM also received a canonical fixture fact that the panel was unreachable
  behind an interlock. It still returned the same unconditional success.
- `airlock_prerequisite`: toughness was treated as enough despite GM-known absence
  of established life support. The condition was actually present in its request.
- `permission_not_access`: the proposal succeeded a goal that made focus open a
  sealed door without an access action. No door-opening consumer was executed.
  This is a dangerous narration claim, not an observed physical engine bypass.
- `withdrawn_goal` and `keywords_without_attempt`: withdrawn intent or merely
  uttering the evaluator's keywords still generated success.
- `calm_synonym` and `walking_synonym`: ordinary composure/endurance descriptions
  were safely deferred because they lacked the recognised wording.

The code explains the pattern: `SyntheticAdjudicator` searches goal text and checks
one selected trait. It does not use the broader GM context to assess prerequisites
or competing demands. These examples expose limitations of that stand-in; they
do not establish how a real model would perform.

Poor/uncertain proposals were not silently endorsed to finish the test. The
fixture controller explicitly completed those native Keep choices separately;
completed GM readback did not mark their proposals as confirmed. This preserves
the distinction between generation, review and native commitment.

## Native behavior and boundaries reviewed

- Sensors produced the native **1/2/3** question counts. The high off-list case
  required the real controller's **incomplete_information** choice. The GM did
  not generate these answers: they were labelled fixture-controller inputs.
- Engage preserved **1/2/3** maneuvers and low/high used-Asset damage; the mid
  cases had no such damage. Maneuvers and Assets came from real owned choices.
- Disobey required an actual superior's recorded order. Its native low result
  could not disobey; mid/high could. All three real order parents completed.
  The GM refused their legitimate child sources, identifying a support gap.
- Flirt preserved the actual target's own reply and the high owed-Tag branch.
  It did not infer the target's response or voluntary follow-through.
- Missing order and missing target requests were rejected with **0 RNG calls**.
  All 38 actual rolls had cached receipt replays without another RNG call.
- All 40 Handler projections excluded the GM and private-target canaries.
  GM generation did receive the private target reply in the three Flirt cases,
  proving that the two projections differ. Proposed public text copied none of it.
- Three completed immediate actions retain separate obligations: punishment;
  Flirt follow-through; and Flirt follow-through plus the owed-Tag dependency.
  Immediate action completion is not proof that all campaign work is resolved.

Two additional integration gaps were directly observed. The conversational GM
returned a typed Play ID for only **22** declarations: the other Play names are
unrecognised, and two legitimate Keep declarations lost identification because
their surrounding text included negation. Completed GM readback rejected all
**14** non-Keep native resolutions because its completion source adapter is still
Keep-only. Native mechanical support and AI facilitation coverage are separate.

## Recommended changes, in order

1. **Replace the keyword stand-in at the GM boundary.** Build the approved AI-GM
   request/proposal path around explicit goal, pressure, stakes, scene facts,
   prerequisites, actual printed choices and outstanding decisions. Evaluate all
   established demands and negative traits, and permit clarification or a scoped
   outcome. Do not add more keywords as a substitute for contextual judgment.
2. **Keep engine validation structural and authoritative.** Require source-bound
   claims and permitted typed effects; reject unsupported access/resource/canon
   changes. The current equality check against the synthetic answer is development
   scaffolding: it would reject a real model's alternative wording or reasoning.
   Replace it with actual contract, authority, stale-context and effect checks,
   not with unvalidated free text. Narrative correctness still needs evaluation.
3. **Add Play-specific outcome adapters and registry-based identification.**
   Sensors needs evidence-backed questions/answers, Engage needs maneuvers/damage,
   Flirt needs target privacy/consent/follow-through, and Disobey needs its actual
   order/refusal branch. These outcomes should not all be converted to a generic
   success/failure test. Preserve engine-owned and participant-owned choices.
4. **Add lineage-aware completion hooks.** Prove legitimate parent/child sources
   and remaining mandatory work. Do not remove the existing parent guard globally
   to make Disobey work. Expose completed receipts, pending choices and follow-ups
   through the appropriate adapter for every supported Play family.
5. **Separate private GM judgment from public/Handler generation.** Give the GM
   full permitted campaign context, but construct recipient-safe output from
   authorised facts and approved plans. Never forward the full GM envelope to the
   Handler. Keep deterministic dice/cost/ownership/replay/consent checks intact.

No real provider is connected by this work. Its selection, data scope and usage
limits remain subject to the standing no-spending instruction. This case pack
should evaluate that later provider as well as the engine boundary. No UI details
are needed to prepare these engine contracts and offline adapters.

## Evidence and reproducibility

`var/director-ruling-audit/index.html` contains the reviewed summary and linked
case results. `results.json` retains every goal, actual native projection, proposed
ruling, review classification and relevant privacy/replay evidence. `summary.json`
contains the exact tested source commit and SHA-256 hashes of the evaluator,
adjudication/conversation/native services and curated JSON. Detailed artifacts are
ignored, synthetic and local; the published tool/fixtures reproduce the run.

Ruff lint/format passed for the new tool. No source-package Python changed, so no
new source mypy scope or repeated local gameplay regression was necessary. Registry,
original planning, repository/manifest and diff checks are retained at delivery.
This is one requested breadth experiment plus review, not a full regression,
independent review, human acceptance, autonomous-live certification or deployment.
External tokens/cost: **0**.
