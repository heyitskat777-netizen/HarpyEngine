# Connected Director follow-through and review

Final implementation/tested source: `7e67492`, following initial implementation
`98246a0` on `2f18cc3`. The owner requested all four recommendations from the
comparison of earlier model tests. Engine work is implemented; the consolidated
[Activity handoff](../integrations/activity/P2_SESSION_UI_HANDOFF.md) specifies
the later UI alterations. No frontend, external provider or live worker is installed.

## Implemented workflows

1. **Actual controller response handoff.** `session.responses` routes a GM-selected
   private question to the actual target controller. Only that controller can
   accept, decline or clarify. Resuming binds their answer to the exact native
   attempt/actor/frame and exposes `target_response` evidence. A refusal cannot
   become a successful voluntary agreement; clarification cannot supply a reaction.
   The native choice owner still independently confirms. Tests cover accept,
   decline, clarification, wrong ownership, cross-goal reuse, consent renewal and
   an explicitly cast Director/NPC under actual original adjudicator authority.
2. **Competing and correcting accounts.** New references can explicitly link
   earlier accounts using `competes_with` or `corrects`. Original text, authorship,
   classification and history are retained. Actor/Handler projections hide links
   and dependency IDs unless both accounts are known. Native approved outcomes
   remain distinct from testimony. Dependency-closed scene handoffs remap links
   and validate original roots across multiple scenes.
3. **Reviewed intervention needs.** Trusted, source-bound GM proposals support
   indirect requests and urgent known reports without adding phrase lists. The
   engine validates exact heard speech/scoped current-source references and
   persists RESPOND/WAIT. A need approval does not approve reply prose: natural
   Handler drafts still require separate private GM review. Operational corrections
   visible to the Handler also qualify as updates, with delivery suppression.
4. **Matched problems and a sustained trial.** A reproducible 112-input rehearsal
   exercises these workflows, actual native Plays, source privacy, original-owner
   confirmations and persistence/retry. Separate fresh Terra reviewers assessed
   archived packets with fixture answers and engine gates withheld.

The optional session `need_provider`/`need_gm` pair runs after knowledge acquisition
and before conversation routing. Defaults remain provider-free. Approved needs can
augment a legacy WAIT; they do not veto an existing eligible request/update or
override a GM-addressed exclusion. Source edits, actual authority/policy changes
and withdrawal/renewal of consent invalidate old need reviews and response handoffs.

## Final connected rehearsal

Command:

```text
.venv/bin/python tools/playtest_connected_director.py --directory var/p2-connected-director-final-checked-20261117
```

| Check | Final observed result |
|---|---|
| Player inputs | **112**, across barracks, hallway, simulation and debrief fiction segments |
| Retained engine scenes | **1**; segment labels do not claim native travel |
| Actual Plays | **3 completed**: Keep Your Head, Check Your Sensors, then a social Keep with a controller response |
| Native dice | **3 rolls**, no rerolls on retry/reconstruction |
| Native original-owner confirmations | **6**, comprising three outcome consumers and three approved readbacks |
| GM declaration interventions | **3** |
| Handler interventions | **12**: four direct, four reviewed indirect, three reviewed urgent, one correcting update |
| Explicit GM response-need reviews | **7** |
| Target controller handoffs | **1**; listening was volunteered without promising forgiveness |
| Prompt privacy | **All 112 narrow Handler prompts checked**, including WAIT turns; no original unreported sighting or GM canary |
| Pending native choices | **0** at completion |
| Durability | Input/confirmation retries, reconstructed services and an actual saved-database reopen pass |

The original unspoken crawler, secondhand jammed-door and negative scout/tarpaulin
problem texts are reused, alongside objective and unknown-enemy questions. The
hidden observation stays private even after an all-clear claim. A different
Pilot's competing observation and the original speaker's correction are attributed
separately; the engine does not manufacture a confirmed enemy. Missing route
knowledge produces clarification. The debrief uses only actual approved readbacks
and retains the target's volunteered limits.

Dialogue, knowledge interpretations, need reviews and confirmations in the long
rehearsal are explicit local **fixtures**. The engine selects actual interventions;
there is no response quota. This is not a model autonomously playing all 112 turns.

## Independent blind audit and resulting fixes

Two new internal agents were explicitly configured as `gpt-6.1-terra`, with no
prior chat/fixture outputs. The Handler received only 27 narrow role packets,
without expected engine gates. The GM received seven knowledge packets and three
actual native outcome packets. History was reused within each role's small batch.
No external provider API or production sampling/cost/latency benchmark was used.

- **Handler: 25/27 initial gate agreement.** The two disagreements were useful:
  acknowledge a secondhand obstruction with scope guidance, and act on a correction
  to an earlier all-clear. Review accepted both interpretations. The first now has
  a source-bound GM need; the second is an engine update when the operational
  correction is actually visible to the Handler. All cited IDs in the independent
  replies were in the supplied role context; the reviewer preserved hearsay,
  uncertain identity, unknown routes and the no-forgiveness limit.
- **GM: 9/10 proposals passed first-pass schema and frozen consumer validation.**
  The Sensor proposal used question-name keys instead of `a1`/`a2` and inferred an
  incomplete-information consequence on the actual mid/listed branch. The engine
  correctly rejected it. Packets now expose `native.answer_contract`; schema
  descriptions and private feedback state the real field mapping/branch. A separate
  informed retry changed only keys and consequence metadata; all answer wording,
  citations and reasoning were preserved. **10/10 validate after that retry**.
- These GM packets are **archived offline validations**, not fresh persisted
  proposals or additional native confirmations. The actual three native consumers
  in the long rehearsal use the explicit fixture provider. The initial comparison
  diagnostic incorrectly decoded strict JSON tuple fields as Python lists; JSON
  transport decoding was corrected before counting model results. No model output
  was changed by that diagnostic correction.
- Final engine actions align with all 27 original Handler judgments **after
  feedback-informed changes**. This is not a second blind success rate, statistical
  accuracy or proof that every subjective intervention judgment is uniquely right.

The longer trial exposed a real pacing regression while applying these findings:
the correction qualified as an update but its delivery key was excluded from the
addressed-reference projection. It repeated, producing 75 interventions in that
intermediate run. A new once-delivered test failed on the same issue. Selection
and suppression now share one eligible-update function. The checked run announces
the correction only at input 42 and suppresses later repeats; intervention count
returns to 12. Intermediate evidence remains retained.

Review also corrected fixture quality: objective fallbacks were too generic for
scope, route and confirmed-outcome questions. The revised fixture uses actual
scope/readback references, preserves report attribution and clarifies an unknown
route. This was fixture guidance quality, not a relaxation of engine citation or
private reply approval requirements.

## Automated verification

- Initial integrated affected selection: **63 passed in 88.26s**, recorded in
  `var/p2-connected-director.xml`.
- Pipeline integration check: **17 passed in 13.92s**,
  `var/p2-connected-director-final.xml`.
- Post-review selection exposed the correction repeat: **1 failed, 30 passed**,
  `var/p2-connected-director-postreview.xml`. Two narrowly targeted fix checks
  subsequently passed.
- Final integrated affected selection after all fixes: **61 passed in 88.39s**,
  `var/p2-connected-director-final-checked.xml`. It covers Handler needs/default and
  reviewed conversation, session, relationships/continuity, GM outcomes/native
  consumers, target handoffs, process restart and the connected mission cycle.
  The three new test files are in CI's explicit focused selection.
- Selections overlap; totals are not additive. **No full regression or remote CI
  run is claimed.** Global Ruff lint/format pass for 2,077 Python files, mypy passes
  959 source files, and runtime registry, planning contracts, offline health and
  repository checks pass. Independent rules/release approvals remain unchanged.

## Evidence and limits

Final readable transcript and event results are under
`var/p2-connected-director-final-checked-20261117/`. Blind inputs, original outputs,
metadata retry and comparison remain under
`var/p2-connected-director-verified-20261117/`. The earlier generic-fixture run and
the intermediate pacing-failure run are retained in their separate directories.
The compact evidence ZIP beside the final transcript includes these relevant
results and checksums, excluding databases and saved runtime configuration.

Semantic GM review remains necessary: hearing plausibility, urgency, paraphrase
equivalence and whether the disclosed controller question matches its framed goal
are not proved by citations. The response contract supports one target per
ordinary Keep; it does not implement blanket multi-target consent. The tested
positive NPC branch uses an actual cast Director and actor-aware native source,
not every possible NPC/body source. Explicit comms remains public scene speech;
selective hearing uses accepted disclosures. History is preserved, not fictional
forgetting, and new prose never applies arbitrary mechanics.

These engine/adapter changes are ready for a **facilitated synthetic playtest**.
Human narrative/pacing acceptance and later Activity controls/authentication remain
open. No external API spending, real campaign capture/write, bot restart,
deployment or Discord publication occurred.
