# Discrete GM / scoped Handler synthetic routing

Owner requested implementation followed by another test, with GM access to all
game information and a separately scoped Handler. Implemented on top of source
`90d54e6f4aca15c5e7613626e84f96b5368af778`; source fingerprint follows below.

## Delivered behavior

Explicit own scene question → GM request with full canonical campaign state and
gameplay records → saved private GM reply → optional separate Handler request
with the original question and actual Handler-known references → saved private
Handler reply. Both routes use separate schemas/providers and independently
retryable keys. Handler input never includes the GM envelope or GM output.

The synthetic adapter answers known objective/scope/status questions from cited
sources, asks for clarification on unknowns, and returns a Play-workflow referral
for mechanics. Recognised Keep Your Head requests include `play_id=keep_your_head`.
The canonical engine remains responsible for executing any actual Play and choices.
The GM's broad input does not become public output. Direct handling invalidates an
old frozen observer batch and excludes only that exact source revision from
routine pending work. Edits re-enter review; other pending input is preserved.

The contract and UI requirements are consolidated in
[the engine handoff](../docs/P2_ENGINE_TRIAL_HANDOFF.md#discrete-gm-and-handler-conversation).

## Actual conversation test

Only 50 Pilot messages were scripted. Four background briefing references were
seeded first; no Handler or GM dialogue was prewritten. Five narrative settings
frame a single conversation: barracks, hallway, briefing, simulated cockpit and
barracks debrief. These labels do not change canonical locations or accept a
mission; this is not five separate 100-message scenes.

| Engine route | Replies | Sourced answers | Clarifications | Play referrals |
|---|---:|---:|---:|---:|
| GM | 50 | 32 | 11 | 7 |
| Handler | 40 | 27 | 11 | 2 |

Observed examples:

- Pilot asks the objective: Handler cites inspection of the relay site and
  reporting observed conditions.
- Pilot asks the authorised scope: Handler cites accessible areas only and
  that forced entry is not authorised.
- Pilot asks who funds the relay: Handler requests clarification; it invents no
  funding source.
- Pilot asks whether a mission is already accepted: Handler cites planning-only
  status; canonical mission state is unchanged.
- Pilot asks Handler to resolve a roll: Handler refers to GM/engine Play handling.
- Pilot asks GM for Keep Your Head and Heat expenditure: typed workflow referral,
  no dice roll or expenditure.

Every GM request contained a GM-only canonical canary. No Handler request contained
it or a Pilot-only reference; Handler requests have no canonical-state or gameplay-
record fields. Saved replies exposed no GM-only canary. Cross-owner reads reject.
Retries made no additional provider calls. Canonical state matched before/after,
dice calls were 0, external tokens were 0 and external cost was 0.

The repeatable command is `.venv/bin/python tools/run_director_trial.py`.
Readable output: `var/gm-handler-conversation.html`; structured output:
`var/gm-handler-conversation.json`. Both remain ignored synthetic artifacts.

## Validation and limits

- Final routing selection: `.venv/bin/pytest -q tests/test_director_conversation.py
  --junitxml=var/gm-handler-trial.xml`: **7 passed in 9.31s**. This includes the
  50-message conversation, privacy, stale source/context, pause/consent, request
  schema separation, route-key conflict, independent failure recovery and observer
  deduplication. Earlier integrated trial selection: **37 passed in 15.81s** before
  expanding the same conversation test from 7 to 50 messages.
- Ruff check/format passed on all 7 changed Python files; mypy passed on all 5
  changed source files. Runtime registry, original planning contracts, repository
  manifest/secret check and `git diff --check` passed; repository findings: 0.
- Remote focused CI includes this routing file alongside the existing selected
  dependencies. Its exact commit/outcome is reported in the delivery message.

These are deterministic source-lookup templates with bounded question categories,
not measured model intelligence, freeform Handler personality or complete GM
adjudication. A future model adapter cannot be dropped into this service: current
output validation deliberately accepts only the exact synthetic reply policy.
New reference topics are backward-compatible defaults; no migration, dependency,
runtime release or bot deployment is included. GM current-scene history/reference
contexts are limited to 100 entries and require reconciliation beyond that limit.
Live publication, automatic orders/mission acceptance, real-provider integration
and the Activity UI remain unfinished. No full regression or human acceptance is
claimed by these focused tests.

Source fingerprint (SHA-256 of sorted filename, NUL, file bytes, NUL for the
5 changed source files, routing test, trial runner and focused CI selection):
`791c18f0a8aaa9667463a1380eb4e245c95ffc954541e53296c359305a57877a`.


## Follow-up: engine-selected interventions over two 100-input scenes

The owner corrected the proposed fixed response count: only generate Handler
speech when the engine decides it is needed. `process_message` now saves a scoped
RESPOND/WAIT decision before any Handler generation. The disposable harness has
100 scripted Pilot messages per scene and no Handler lines, route flags,
expected-reply markers or reply quota. Player names are synthetic display aliases
bound to the actual fixture principals. GM replies remain separate diagnostics.

| Scene | Pilot inputs | Handler replies | WAIT | Direct-question replies | Scope warnings |
|---|---:|---:|---:|---:|---:|
| Barracks / hallway | 100 | 10 | 90 | 10 | 0 |
| Relay mission simulation | 100 | 11 | 89 | 10 | 1 |

Barracks Handler replies occur at visible chat messages **8, 17, 30, 38, 46, 56,
68, 78, 88, 100**. Simulation replies occur at **8, 17, 30, 38, 46, 56, 68, 78,
88, 100, 102**. These are observed output positions, not a planned schedule.
Each transcript also records the triggering player-input number, decision reason,
actual reply, citations and saved reply ID. Final visible lengths are 110 and 111
messages because Handler output is additional to the 100 Pilot inputs.

The simulation's input **91** states a plan to force the sealed door without
addressing the Handler. The engine selects a scope warning at chat **102**, citing
its known prohibition of forced entry. It chooses no action and grants no
mechanical outcome. Simple Handler mentions and negated forced-entry plans remain
silent. Each scene also yields two clarification requests for unknown facts and
one Play referral; the other replies cite known briefing facts. No broad reasoning
or persona quality is claimed: the trigger policy is deterministic and narrow.

Actual command: `.venv/bin/python tools/run_handler_scene_trials.py`. Both scenes
completed with 100 GM processing calls each, 0 external tokens/cost, 0 dice rolls,
unchanged canonical mechanical state, 0 pending input and successful replay with
no new generation. GM-only and Pilot-only canaries stayed out of Handler context
and replies. Temporary databases were disposed. Readable output is
`var/handler-long-scenes/index.html`; `transcripts.txt` is plain text, and scene
JSON contains all 200 RESPOND/WAIT decisions and separate GM diagnostics.

To support 100 inputs plus four setup observations, GM history now explicitly
reports omitted raw entries and supplies the latest 100 in chronological order.
At each scene's end, 4 old setup observations are outside that raw window. The
separate current reference context and full canonical state remain available;
there is no automatic summary of omitted dialogue. Reference contexts retain
their existing 100-reference limit.

Focused validation on the integrated source: `tools/run_director_trial.py`:
**38 passed in 22.45s**, including silent/direct/scoped/negated/GM-directed needs,
immutable decision replay, denial of generation from WAIT and stale-decision
rejection. Ruff check/format covers all 4 changed Python files; mypy covers both
changed source modules. Repository/manifest check: 0 findings. No new migration,
model integration, deployment, real observation or publication is included.

Runtime-and-dialogue snapshot SHA-256 (sorted filename, NUL, bytes, NUL for the
2 changed engine modules and 2 dialogue fixtures): `c9d032c326448abf70fcf1acddc0134082d2558d342eecd8da5822f249ba66a6`.


## Follow-up: native Plays plus visible GM and Handler intervention

The owner requested Plays in the long scenes and visible GM intervention alongside
Handler intervention. The new `--plays` mode retains two 100-player-input scenes,
with three actual ordinary native Keep Your Head workflows per scene. These are
not fabricated rolls or merely referrals: existing GameService/GameWorker execute
locks, receipts, choices, completion and fake delivery using disposable fixtures.

| Scene | Visible GM interventions | Optional generated Handler replies | Required Handler owner rulings | Native rolls |
|---|---:|---:|---:|---:|
| Barracks / hallway | 7 | 8 | 3 | 3 |
| Relay simulation | 8 | 9 | 3 | 3 |

Each scene consumes one roll per actual Play: **[2,3] → 5/low, [4,5] → 9/mid,
[6,6] → 12/high**. Faces are a test-only injected schedule, never chosen by the
GM or Handler providers. All fixture Heat choices are 0. Canonical state changes
in the disposable campaigns, including the Pilot's chosen high-tier Tag; the old
zero-roll/unchanged-state statements apply only to earlier no-Play trials.

Visible labels distinguish GM intervention (blue), optional Handler speech (teal),
actual engine workflow (grey), and explicitly scripted owner choices (gold).
Required Handler rulings are gold test-controller inputs responding to real engine
`handler_keep` choices. They are not counted as optional AI dialogue or inferred
from a dice tier. Private required-Handler explanations are withheld.

The first episode in each scene starts at player input 20 / chat 22:

- **23: GM** selects a typed Keep Your Head request.
- **24–25: engine** creates the confirmed action, acquires the lock and records
  exactly one original 2d6 receipt. No RNG occurs before lock acknowledgement.
- **26–28: choices** each participant explicitly passes Tags and the original
  Pilot supplies the actual printed traits/Tag options for the rolled tier.
- **29: engine** requires the original Handler's enough/not-enough ruling; GM
  readback is actually attempted and rejected as PLAY_PENDING until it is supplied.
- **30: Handler controller** explicitly submits the required test ruling; private
  explanation stays hidden. The actual engine completes the Play and releases the lock.
- **31: GM** reads back only proved receipt/total/tier, without inventing mission
  success, access or cancellation of another Play.

The next Play request/completion pairs are **66/74** and **96/104**; required
Handler rulings are at **73** and **103**. Optional Handler replies in barracks
occur at **8,17,39,48,56,86,114,126**. The simulation adds a scoped warning at
**129**, immediately after **GM adjudication at 128** for input 91's forced-door
proposal. Each transcript has a complete linked intervention index and receipt
summary. Final visible scene lengths are **136** and **138**, including workflow
and choice entries in addition to the 100 player lines.

GM routine reviews still receive broad context, but their saved `gm_decision`
distinguishes WAIT from visible RESPOND. Ambient review does not produce a visible
clarification after each message. New owner-private `review_play/get_play_review`
reuse the observer's full native source proof, rechecking it atomically with the
saved readback. Only current own original Pilot results are accessible. Completed
source revisions already read back are excluded from routine pending work.
Native choices and unsupported Play families never become automatic AI commands.

Actual commands and results:

- `.venv/bin/python tools/run_handler_scene_trials.py --plays`: both scenes
  completed, **6 native rolls/6 completed Keeps**, 200 GM reviews, 17 optional
  Handler replies, 6 required Handler fixture answers and 0 pending inputs.
- Every begin, choice, roll receipt and GM-review replay preserved the existing
  result without extra dice. Readback applied no additional mechanical changes.
  GM-only, PC-only and private required-Handler canaries stayed out of Handler
  generation and visible GM output. External tokens/cost: **0**.
- `.venv/bin/python tools/run_director_trial.py`: **39 passed in 20.81s**. New
  checks cover GM silence/request gating, premature readback, actual mid-tier
  completion, foreign-owner rejection, private-text exclusion, replay and pending
  input deduplication; existing source-proof checks remain passing.
- Ruff lint/format passed on all **6** changed Python files; mypy passed on all
  **3** changed source modules. Repository/manifest check: **0 findings**.

Artifacts: `var/gm-handler-play-scenes/index.html`, `transcripts.txt`, per-scene
JSON, `summary.json` and `source-snapshot.json`. Engine policies are deterministic;
fixture owners choose all voluntary inputs. This is six instances of native Keep,
not coverage of every Play. No live campaign, model integration, bot deployment,
real capture, automatic general Play consumer or autonomous publication is claimed.

Source snapshot SHA-256 (sorted filename, NUL, bytes, NUL for the 3 changed source
modules, routing test, 2 trial tools and 2 new dialogue fixtures):
`a4793cbb5a050068884b43bc4931c0f7016e26c05f1fe20cd8b26f2c7835b331`.

## Follow-up: contextual GM judgment before owner confirmation

The owner clarified that Keep's actual positive/negative traits must be judged
against the narrated goal. The previous demonstration did not do that: its
owner outcome flags were scripted by tier, and the GM only reported a receipt.
That earlier limited evidence is not evidence of narrative adjudication.

New `DirectorAdjudicationService` binds a private GM proposal to the original
accepted declaration/native context, actor/incarnation/participants, receipt,
committed actor traits, action revision and pending original Handler choice.
It supplies verdict, enough value, goal, reasoning, narration and citations.
Generation runs outside the writer lock and proof is rechecked before saving.
Foreign actors, substituted context, invalid output and changed native choices
reject. No raw GM envelope is saved or forwarded to the Handler dialogue provider.

The bounded synthetic GM assesses concrete endurance/control situations; these
are discretionary interpretations, not printed universal trait-success rules.
Unknown goals or unestablished relevant traits request clarification. Other Play
families explicitly require their own outcome adapter; Keep's binary test is not
applied to them. Broad natural-language judgment remains unfinished.

Native focused tests keep the actual roll at **9/mid**:

| Goal | Actual ARE | Actual ARE NOT | GM verdict |
|---|---|---|---|
| Hold the calibration needle precisely | tough, in control | desperate | success |
| Same precision goal | tough, vicious | in control | failure |
| Endure the freezing corridor | tough, vicious | in control | success |

This changes the result with the choices, then with the goal while keeping the
choices fixed. The GM is not given a verdict. The original Handler test controller
confirms the computed enough value and GM reasoning/narration through the native
choice. The fixed `tier != low` fixture ruling is removed. Completed GM readback
recognises a confirmed proposal only when native response/actual enough, original
source revision/context and saved proposal agree. It does not copy arbitrary
private Handler text. Proposal generation/replay commits no mechanical effects.

Both updated 100-input scenes completed with the following observed results:

| Scene | Visible GM posts | Optional Handler replies | Native owner confirmations | GM goal verdicts |
|---|---:|---:|---:|---|
| Barracks / hallway | 10 | 8 | 3 | success, success, failure |
| Relay simulation | 11 | 9 | 3 | success, success, failure |

Each demonstrates **5/low + tough → endurance success**, **9/mid + in control →
focus success**, **12/high + not in control → precision failure**. Contextual GM
proposals are at chat **29,73,104**; native owner confirmations at **31,75,106**;
confirmed GM readbacks at **32,76,107**. Final visible lengths are 139 and 141.
Updated HTML/text/JSON and source snapshot remain under `var/gm-handler-play-scenes/`.

Actual validation:

- `.venv/bin/python tools/run_director_trial.py`: **42 passed in 22.57s**.
  New checks cover the three mid-tier cases, unclear goal/other Play adapter,
  unbound context, foreign ownership, invalid provider leakage, native choice
  changes during generation, proposal replay and matching confirmed narration.
- `.venv/bin/python tools/run_handler_scene_trials.py --plays`: both scenes
  completed, **6 native rolls**, **4 computed goal successes / 2 failures**,
  6 explicit owner confirmations, 200 private GM reviews, 17 optional Handler
  replies, 0 pending inputs, 0 external tokens/cost and Heat choices of 0.
  Native high-tier Tags remain real disposable state. Captured proposals pass
  strict JSON validation; visible GM/Handler private-canary checks pass.
- Ruff lint/format passed over all **7** changed Python files; mypy passed on all
  **3** changed source modules. Registry, original planning, repository/manifest
  and diff checks passed; publishable findings: 0. Remote focused CI includes
  the three new native adjudication tests.

This is bounded synthetic Keep judgment, not completed adjudication of every Play
or a live model test. No migration, paid inference, deployment, live campaign
change or autonomous publication is included. Source snapshot SHA-256 (sorted
filename, NUL, bytes, NUL across 3 source modules, test, 3 tools, 2 dialogue
fixtures and CI selection) is recorded in the ignored source snapshot.
