# Director model-contract revision and retest

Implementation and tested source: `d7de985`, based on `1ea24cd`.
The owner accepted the six recommendations from the
[delegated Terra review](P2_TERRA_MODEL_REVIEW.md) and requested revision/retesting.
This increment closes those bounded adapter gaps for assisted synthetic testing.
It does not install an external provider, Activity UI or live worker.

## Implemented changes

| Earlier discrepancy | Revised behavior |
|---|---|
| Raw mixed narration entered the Handler question | Reviewed mode sends scene/mixed/unclassified text through GM speech classification. Only accepted exact quotes for that listener enter the Handler question. Private sources cannot disclose speech; unclassified silence stays neutral. |
| First reports required an already recorded fact | New `testimony` accepts an actual spoken claim without a prior reference. It preserves current words, uncertainty, attribution and negation as a reported claim. It applies no world effects. |
| Names and paraphrases lacked supporting contracts | GM packets include an authenticated native actor/name/controller directory. `paraphrase` links actual current speech to a speaker-known prior reference; `reported_by` preserves the source actor through scene continuity. IDs remain authority. |
| Natural Handler prose failed exact-template matching | Explicit `handler_mode="reviewed"` supports injected natural replies, real scoped citations, engine RESPOND gating and private GM review. The synthetic default is unchanged. |
| Schema success hid backend failures | Exported schemas express mandatory source/native citations and conditional prior references; private structured feedback explains schema/citation/ownership errors without echoing raw source input. Unknown Handler information uses `clarification`. |
| A social ruling assumed control of its target | Strict Keep frames declare self/other/unresolved response scope. Other scope binds a native actor/controller/cast; unresolved or player-owned voluntary reactions cannot receive a settled GM verdict through this adapter. |

Reviewed Handler generation returns `reply=null` and
`status="awaiting_gm_review"`. A GM inspects grounding/disclosure, then explicitly
approves or rejects the unchanged draft. Approval rechecks the source actor,
revision and role context, creates one private exchange and applies no mechanics.
Valid citation IDs alone do not prove the prose is supported. A regression test
deliberately gives valid citations to invented enemy prose and keeps it private
until rejection. Source edits also prevent stale approval.

Default session outcome construction enables strict response ownership when its
conversation service uses reviewed mode. Independently constructed outcome
services must opt into `require_response_scope=True`. Legacy synthetic fixtures
retain compatibility. Scope is a trusted facilitator declaration, not automatic
natural-language inference; declaring a listener-dependent goal as self-scoped
would still be an incorrect interpretation requiring review.

## Fresh delegated Terra retest

Two fresh internal agents were explicitly configured as `gpt-6.1-terra`: one GM,
one Handler. They received actual packets for their own role, without historical
outputs, fixture verdicts or each other's packets. There were **19 decisions**:
seven knowledge proposals, five actual native Keep proposals and seven Handler
turns. Role history was reused within each small batch; these are not 19 fresh
independent model instances or an external API benchmark.

| Check | Observed result |
|---|---|
| GM proposal schema and engine replay | **12/12 accepted first pass**; no citation repair or metadata refresh. |
| Knowledge | **7/7 accepted**: private perception, mixed hidden enemy/spoken all-clear, uncertain hearsay, unspoken ambiguous sighting, private prompt injection, negative report to a native named Pilot, and later paraphrase. Actual recipient sets and report source actors were checked in stored references. |
| Native contextual Keep | **5/5 accepted**: precision fails, endurance succeeds, unidentified social target clarifies, calm delivery succeeds, another Pilot's agreement clarifies. Three synthetic native owner confirmations completed; two remained held. Five source rolls, no provider-caused rerolls. |
| Handler RESPOND/WAIT | **7/7 model decisions matched** the engine gate and the model's separately requested response-need assessment. Four RESPOND, three WAIT. The Handler saw the engine decision; this is agreement evidence, not a blind gate-accuracy metric. |
| Natural draft transport | **3/4 first pass**; **4/4 after one label-only feedback retry**. All four subsequently passed explicit local GM review into private exchanges. No automatic publication. |
| Private information | Actual Handler requests excluded private sighting/injection canaries, the concealed catwalk enemy and the unspoken grey shape. The mixed request contained only the approved all-clear/question. |

The one initial Handler failure was an appropriate unknown-position reply:

> I don’t know which side has enemy units. I have no confirmed location to give you.

It used `disposition="answer"` with no citations. The consumer rejected it because
factual answers require citations. A separate informed retry changed only the
label to `clarification`; wording, citations and response decision were identical.
The schema now states this cross-field requirement and private feedback explains
the correction. Both original and retry are retained. This does not count as a
fourth first-pass success or a new blind sample.

The mixed hidden-enemy case produced:

> You may inspect the relay within the exercise limits; forced entry is not authorised. Report what you find.

The Handler did not mention the concealed enemy. In the hearsay case it retained
“the cook said,” “might” and “you have not checked,” then requested verification
without forced entry. The paraphrase moved a later report of the private drone
sighting to the Handler while retaining speaker provenance; it did not establish
independent truth or expose the original private aside.

## Automated verification

- Integrated affected selection: **51 passed in 72.41s**,
  `var/p2-contract-revision.xml`. It covers the new contracts plus knowledge,
  continuity, outcome consumers, session, restart, console and mission-cycle paths.
- After the final Handler schema/feedback addition: **18 passed in 24.46s**,
  `var/p2-contract-final.xml`. Exact selection:
  `test_gm_response_ownership`, `test_knowledge_contract_revision`,
  `test_handler_contract_revision`, `test_director_session`,
  `test_director_process_restart`, `test_p2_player_console`, and
  `rules/test_p2_mission_cycle`.
- These selections overlap and are not additive coverage totals. No full
  regression was repeated. Three new test files are included in CI's explicit
  focused selection; no remote CI run is claimed.
- Global Ruff lint/format pass (**2,070 Python files**); mypy passes for
  **958 source files**. Runtime registry, retained planning contracts, offline
  health and repository checks pass. Registry/rules approvals are unchanged.
- Offline packet tools prepare/replay supplied JSON and make no model API calls.
  Artifact assertions check all proposal schemas, actual response gates,
  citations, hidden-text exclusions, acquisition recipients/provenance, unchanged
  dice counts and the exact one-field retry. A local evidence-builder diagnostic
  initially treated private perception claims as relayed testimony; that check
  was corrected to require `reported_by` only for report/testimony/paraphrase.
  No engine result or model candidate was changed by that diagnostic correction.

## Handoff, evidence and remaining limits

The [consolidated Activity handoff](../integrations/activity/P2_SESSION_UI_HANDOFF.md)
now specifies channel controls, disclosure/actor metadata, knowledge feedback,
private Handler review and response-scope controls. These are Python service
contracts; HTTP/authentication/frontend integration remains separate work.

Local synthetic evidence:

- `var/terra-contract-retest/transcript.md` — readable sources, GM rulings and Handler turns.
- `var/terra-contract-retest/summary.json` — counts and checked boundaries.
- `var/terra-contract-retest/HarpyEngine-model-contract-retest.zip` — original
  packets, schemas, outputs, first-pass failure, feedback retry, stored acquisition
  projections, results and SHA-256 manifest. Synthetic databases are excluded.

Explicit `comms` is **public scene speech**, not a private DM or selective radio
channel; its whole text can enter the Handler's current question. Selective
hearing uses accepted mixed/unclassified disclosures and actual listeners. A named
addressee selects knowledge acquisition recipients in the trial but does not make
public comms secret from other in-scene listeners.

Speech classification, hearing plausibility and paraphrase equivalence still
require semantic GM judgment. Citation checks do not prove entailment. The
positive explicitly cast GM-controlled NPC branch is implemented but was not
exhaustively integration-tested here; player-owned and unresolved response holds
were tested. No generic target-consent endpoint was added. Existing original
choice owners, native mechanics, safety/consent/freshness, default-empty specialist
scope and append-only histories remain authoritative.

The next useful step is porting these explicit review/input controls into the
Activity and running a short facilitated session for pacing and semantic quality.
This small internal model sample is not autonomy certification, a production
provider benchmark or human acceptance. No external API spending, real campaign
capture/write, runtime deployment, bot restart or Discord publication occurred.
