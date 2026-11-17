# Knowledge acquisition and role isolation

Implemented source/tests: `8c1cec4`, continuing `ad496fa`.
The engine now accepts typed, source-bound GM knowledge proposals and can process
them before Handler routing when a trusted GM provider is configured. History is
append-only; this does not implement fictional forgetting or change mechanics.

## Implemented boundary

`DirectorKnowledgeService`, available as `DirectorSessionService.knowledge`,
provides GM-only pending sources, source packets, proposal generation/storage,
private review, fresh confirmation and a complete `acquire` path. A proposal
selects exact source quotes and actual actor recipients rather than copying an
entire message into everyone's knowledge.

- A **perception** proposal from a message is limited to its originating actor's
  claim. It does not establish an enemy/world entity or give other roles sight.
- A **report** requires an explicit comms source and a real reference already
  known to its original speaker. Only selected current actors learn its quoted
  content. It remains a reported claim; private prerequisites and unrelated
  source asides stay outside the recipient's projection.
- An **outcome** requires an actual confirmed native GM readback. Message prose
  cannot grant confirmed-outcome classification or bypass a Play's real owners.

Proposals bind original source/version, current context, actual actor identities,
scene scope, consent and safety. Confirmation rechecks those inside the write
transaction. Duplicate facts/recipients cannot be applied again under a new
proposal; exact retries reuse their original results. Source edits require
reconciliation. Retirement preserves the old reference and source history.

`DirectorSessionService` optionally accepts both `knowledge_provider` and
`knowledge_gm` as trusted server configuration. With both configured, `submit`
saves the input, generates/validates/applies its knowledge proposal, then processes
the conversation. A provider may return no updates. Failure after acquisition or
GM reply resumes under the original command without repeating acquired knowledge
or successful provider work. Supplying only one constructor option is rejected;
the default path remains provider-free.

The second part of the boundary is input delivery. A new
`AppendSceneInput.fictional_channel` distinguishes `scene` (legacy scene speech),
`private` and `comms`. The Handler receives a neutral heartbeat instead of private
current-message text, even through a direct Handler route. Filtering references
alone would otherwise leave a leak through the question field. Private narration
cannot be reassigned to another actor through the legacy reference API, and an
edit cannot turn an old private input into a comms message.

This channel describes fictional hearing, not new Discord DM/OOC privacy. The
existing synthetic scene audience/consent remains unchanged. Adapters must mark
private narration before routing; styling or words like "I do not report it" are
not a replacement for that field. The current local console still sends ordinary
scene speech; the new fields/provider path are engine APIs awaiting UI controls.

## Review tests and observed results

The six new tests invoke real scene/knowledge/conversation/native-outcome services
with injected local GM interpretations and captured provider requests.

| Scenario | Observed result |
|---|---|
| Pilot sees a silver enemy drone behind the eastern relay, withholds the report and includes private grid details | The Pilot gains only the selected sighting quote. The GM sees the source; the Handler waits. The hidden enemy and grid details are absent from Handler knowledge and prompt. |
| Pilot asks the Handler to repeat the established objective without mentioning the enemy | The Handler instructs them to inspect the relay site and report conditions. Its actual request and reply contain no hidden enemy. Even forcing a direct route from the private input does not expose it. |
| Pilot subsequently reports the exact sighting over comms | The selected Handler gains the reported claim and produces a tactical update. The other Pilot does not gain it. Private grid details and the GM's private reasoning remain excluded. |
| Another Pilot privately observes a separate sniper | That observation is held by its own actor; neither the first Pilot nor Handler receives it. |
| GM tries to invent a quote, give private perception to the Handler, upgrade message prose to truth, use an unknown actor, or report another Pilot's private knowledge | Engine validation rejects the proposal/legacy assignment. A duplicate accepted fact is also rejected. |
| Actual native Keep completion and approved narration | The chosen Handler can learn its confirmed outcome through the acquisition adapter. An unselected Pilot gains no reference; the acquisition applies no additional native effects. |
| Provider failure, stale source and consent withdrawal | No partial knowledge is applied. Retry succeeds under the original key. Stale confirmation and withdrawn consent block application; old references remain in history after explicit retirement. |
| Database restart and closed-scene handoff | Accepted knowledge survives; recipient restrictions and hidden dependencies remain intact. |
| Configured automatic session, then Handler failure after acquisition | Knowledge is processed before Handler response. The retry reuses acquired references and prior GM generation. Three inputs produce three knowledge-provider calls despite retries. |

The generated trace at `var/p2-knowledge-acquisition.json` records the actual
before/after Handler replies. The first response is the established relay
instruction. The later response is:

> Recorded tactical update: Reported claim: a silver enemy drone behind the eastern relay

## Verification

- Broad integrated candidate: **60 passed in 69.03s**, zero failures/errors/skips
  (`var/p2-knowledge-candidate.xml`). This preceded the final private-review accessor
  and optional per-submit provider wiring.
- Final affected run: **11 passed in 17.78s**, zero failures/errors/skips
  (`var/p2-knowledge-final.xml`). It includes all six acquisition/isolation cases,
  session coordination, local console compatibility and the complete mission cycle.
  These runs overlap; they are not 71 distinct cases.
- Global Ruff lint/format pass (2,060 Python files formatted), and mypy passes
  for 958 source files. Runtime registry, original planning package, offline CLI
  health and repository checks pass. No migration or release-policy change.
- Reproduce the focused knowledge review with
  `.venv/bin/pytest -q tests/test_director_knowledge.py`.

No new full regression, Activity-bundle/browser run or human acceptance occurred.
No spending, external model call, live capture, campaign mutation, deployment,
restart or Discord publication occurred. The GM interpretations are explicit
synthetic fixtures, not evidence that a real model reliably understands arbitrary
roleplay. The engine checks grounding and scope; semantic interpretation and
hearing plausibility still belong to the GM/provider. There is no installed
model, autonomous worker, sight-line simulator or general free-text fact parser.

The next integration work is the private/comms UI control and GM acquisition
review/worker path in the Activity, using the updated
[consolidated handoff](../integrations/activity/P2_SESSION_UI_HANDOFF.md). Preserve
the selective-observer schedule and existing release gates. Then review a human
scene for missed disclosures, unwanted interruptions and mistaken interpretations.
