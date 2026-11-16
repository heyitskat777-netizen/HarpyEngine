# Engine-first synthetic Director trial

Owner direction: finish engine work independently; UI changes are delivered later.
Model preference is tentatively GPT-6.1 Terra. No provider identity or compatibility
is asserted and no external inference/spending is authorized. Default providers
are local fixtures; manual proposals are explicit facilitator judgments. Neither
is measured or emulated model intelligence.

## Current candidate: structured GM adapter v2

Use `GMAdapterService(context, provider=None)` for new contextual ruling work.
The old `DirectorAdjudicationService` and long-scene `--plays` path retain their
historical v1 keyword experiment; do not treat those as the new provider boundary.
The [candidate report](../reports/P2_GM_ADAPTER_PLAYTEST.md) records repeated
implementation, 40-case review and the resulting offline playtest scope.

```bash
.venv/bin/python tools/playtest_gm_adapter.py
.venv/bin/python tools/playtest_gm_adapter.py --list
.venv/bin/python tools/playtest_gm_adapter.py --case precision_control_mid --interactive
.venv/bin/python tools/audit_director_rulings.py --protocol
```

The console uses the pinned dev/test fixtures and disposable synthetic campaigns.
Interactive mode exports `request.json` and `proposal.json` under
`var/gm-adapter-playtest/<case>/`; edit the latter in another editor and press
Enter. The default proposal asks for clarification. An accepted enough/not_enough
proposal still needs explicit original-controller confirmation in the console;
declining or asking for clarification leaves the native choice pending.
The console's temporary database is removed on exit. Pilot, target, Tags and
non-Keep owner answers are labelled fixture scripts, not invented AI decisions.
`--goal` requires `--interactive --frame FILE` with explicit stakes, demands and
intent. This tests the contract, not a persistent campaign or natural-language GM.

The backend service contract is:

- `.evidence(viewer, scene, source_id, source_revision, action_id) -> GMPacket`:
  configured administrator only; original accepted Pilot declaration, actual native
  receipt, traits, stage/choices, Disobey parent proof, private canonical context,
  source references and latest 100 scene inputs with an explicit omitted count.
- `.frame(viewer, key, scene, source_id, source_revision, action_id, task)`:
  configured facilitator records explicit goal stakes, distinct demands, intent
  and evidence-bound prerequisite interpretations. Scene conditions left unknown
  cannot produce a resolved Keep verdict. This does not make traits automatic
  rules or convert narration into mechanics. Changed context requires reframing.
- `.evaluate(viewer, key, scene, frame_id)` calls `GMProvider.propose(packet)`
  outside the writer lock, validates its strict `GMProposal` against actual
  evidence/trait polarity and demand coverage, then rechecks context in the save
  transaction. Valid wording need not match any synthetic oracle. No dice or
  world/resource effects are supplied by the provider. Default provider requests
  Keep review; other Plays retain native pending/complete results.
- `.private(viewer, scene, proposal_id)` is GM-only. `.view(viewer, scene, id)`
  returns fixed safe wording and the existing native participant projection,
  confirmation/currentness, own pending choice/work kinds, immediate completion
  and known action/scene follow-up completion. Private reasoning, task annotations,
  raw GM context and other owners' work details are excluded.
- `.confirm_keep(viewer, key, scene, proposal_id)` uses the original native
  `handler_keep` choice owner. It revalidates source, consent, context and proposal
  inside the native response transaction. Same-key exact retries return the saved
  response without rerolling. An administrator cannot impersonate that owner.

For the later Activity: add a private facilitator framing/proposal panel, a
separate original-controller confirm control enabled only by `can_confirm`, and
participant refresh using `.view`. Show pending choices and follow-ups separately;
refresh/reframe stale proposals. The server must derive `GuildViewer`, campaign
and role from authenticated sessions; never pass a client-supplied authority flag.
Keep the fictional Handler's scoped conversation route separate from the private
GM review even when one human controls both. These are Python services, not HTTP
routes. Existing consent, knowledge and delivery requirements below still apply.

Ready for attempted **offline five-Play adapter playtesting**. Real provider
transport, bounded usage/data handling, human narrative/fairness evaluation,
broader Playbook/child consumers, general generated narration, autonomous
publication and Activity delivery remain separate unfinished work.

## Implemented engine flow

1. Existing bound synthetic scene, current membership/actor binding, off/shadow
   observation policy and each participant's explicit consent.
2. IC source revisions, original audiences, native Keep receipt trigger, durable
   quiet/size/age batches, claim tokens, pause/stale/recovery protections.
3. Authorized facilitator records each source as a reference in explicit scene
   order, with prior-reference dependencies and explicit known actor bindings.
   Text remains a reported claim or a committed-Play reference; it grants no
   mechanical/canonical state. Updated source/knowledge records supersede previous
   reference views without deleting history. Source corrections require explicit
   reconciliation. Real fictional time, cross-scene causal reconciliation and
   rules-driven memory loss are not implemented by this local reference order.
4. GM and actual Pilot/Handler contexts are projected separately. Actor views omit
   unknown references, other actors' knowledge assignments and hidden dependency
   IDs. Canonical profile/controller/cast checks apply. NPC knowledge requires its
   actual presence/control adapter and remains blocked.
5. Claimed source coverage must be complete before shadow evaluation. A local
   provider runs outside the writer transaction; strict decisions support WAIT,
   REQUEST_PLAY, NPC_DIALOGUE, WORLD_EVENT_PROPOSAL and NEEDS_REVIEW. Unsupported
   actor/rule/effect claims reject. One invalid-output retry is allowed; errors
   are sanitized. WAIT acknowledges current input; other valid proposals are
   private review work. Failures consume no input. No narration is published.
6. Outcome and frontier acknowledgement commit together; old saved outcomes can
   reopen after source correction. Replays return the saved result. Optional
   approve/reject review is append-only and applies/publishes nothing.

Run the repeatable synthetic trial with pinned dependencies:

```bash
.venv/bin/python tools/run_director_trial.py
```

It uses disposable pytest databases, fake clocks/providers and synthetic identities.
It does not start a bot, collect player text, call a model or mutate a live campaign.
JUnit output is `var/p2-engine-trial.xml`. This is a synthetic shadow trial, not
human acceptance or an autonomous-live readiness claim.

## Backend contracts for the later UI implementation

Preserve the delivered summary v1 contract. New engine services are:

- `DirectorContextService(observations).record(viewer, key, scene_id, source_id,
  expected_order, known_by=tuple[ActorRef,...], dependencies=tuple[str,...])`:
  current configured facilitator in the consented scene; server verifies sources,
  ordering and actual actor control. New reference records can explicitly disclose
  or reconcile a corrected source. Same-source same-revision grants retain prior
  actor knowledge; a corrected text requires an explicit new assignment.
- `.build(viewer, scene_id, actor=None) -> DirectorContext`: GM requires configured
  administrator; an explicit actual actor requires its current controller. Source
  staleness fails closed. At most 100 reference records; no silent truncation.
- `DirectorShadowService(context, provider=None).evaluate(viewer, scene_id, run_id)`:
  GM-only current claim; local default provider. `.get(...)` reopens a saved result
  under current membership/consent. Worker tokens are retained server-side.
- `.review(viewer, key, scene_id, run_id, decision='approve'|'reject')`: records one
  immutable GM decision for reviewable proposals; retry with the same key. Reopen
  it via `.get(viewer, scene_id, run_id + ':review')`. Approval supplies no mechanic,
  player choice, consent or publication authority.

The eventual UI needs: scene/role selector from verified permitted choices;
IC/OOC source submission and consent notice; current pending human choices;
source/reference citations with clear claim/result labels; facilitator knowledge
assignment and source-correction review; private shadow proposal/review queue;
status/refresh/reopen across reloads; clear off/shadow and blocked-application
states. Escape all returned text. Browser flags, posted actor ownership, model
output and nicknames never authorize an operation. Keep IDs as strings.

No framework, HTTP routes, session transport or realtime bus is selected here.
Those will be mapped to the Activity's actual implementation after engine scope
is settled. No separate campaign database or browser SQL is needed.

## Gates still open before autonomous live trial

This checkpoint is ready to exercise the documented synthetic shadow flow only.
NPC presence/knowledge and legal dialogue consumers, world-event/Play command
consumers, narrow autonomy policy, delivery with final audience/safety checks,
real-data consent/retention/redaction, installed worker lifecycle and independent/
human fairness/pacing review remain unfinished engine or operational work.
Cross-scene chronology and broader Play sources are also unsupported. A real model
trial additionally needs verified provider/model configuration and explicit usage
limits; the current no-spending direction remains in force. UI integration is
intentionally deferred and is not used as a blocker for further engine development.

## Subsequent actual-role dialogue integration

NPC contexts now reuse ActorService controller proof and require an actual living
explicit cast role. This supports an NPC controlled by a current scene participant;
NPC-only controller audience reconciliation remains unsupported. NPC names,
private detail and goals are not copied from raw world state into generation.

`DirectorDialogueService(context)` supports:

- `draft(viewer, key, scene_id, actor, expected_context, source_refs)`: actual
  controller chooses an NPC/Handler and known reference IDs; Pilot speech is
  prohibited. The synthetic text quotes those references as reports, supplying
  no invented feelings, choices or mechanical outcome. All selected sources must
  belong to that actor's authorized context. Result is a metadata-only draft ID.
- `get(viewer, scene_id, id)`: current original controller/scene/role authorization;
  returns its own saved draft/review. No administrator ownership override.
- `review(viewer, key, scene_id, id, decision='approve'|'reject')`: immutable
  controller approval/rejection, with fresh context and safety checks for approval.
  Every result still blocks application and publication. Orders, disclosures with
  actual effects and freeform generated speech need their exact future consumers.

This extends the synthetic engine trial to actual NPC/Handler contexts and private
extractive dialogue. It does not provide autonomous/live publication or a model
persona. Earlier statements about NPC adapters above refer to broader NPC-only
participation, physical travel, automatic knowledge and action consumers.

## Source-proved synthetic report projection

`DirectorContributionService(dialogue)` now provides a narrow engine-only trial
path after a controller approves an extractive NPC report:

- `commit_synthetic_report(viewer, key, scene_id, draft_id, venue_id)` verifies
  current role/context/review, scene lock/safety, actual NPC position/reachability
  and protected-room policy. `venue_id` must resolve to an existing source-GM
  Matrix scene/location context through its original proof helper; unknown venues
  are blocked. No new Frame capability, travel or invented location is granted.
  The report template is recomputed from actual known references. A stable stored
  contribution and audit/command outcome commit atomically; retries reuse its ID.
- `projections(viewer, scene_id)` rechecks current scene membership/consent, safety,
  chat locks, actor controller/casting/position, source knowledge and privacy.
  It returns stable scene contribution IDs, generic speaker attribution and report
  text, omitting hidden NPC identity/controller/venue/assignment metadata. Missing
  current proof suppresses optional output; existing required receipts are separate.

This is an explicitly requested, synthetic-only projection, not autonomous live
publication. The later UI can poll/refresh this projection and render by stable ID;
no network transport, actual player-data collection or real inference is installed.
Handler/public speech, other venue sources, unsought contribution pacing, general
NPC prose, mechanical/world effects and a durable network delivery worker remain
unsupported. Engine-first development continues without making UI details a blocker.

## Discrete GM and Handler conversation

`DirectorConversationService(context, gm=None, handler=None)` adds direct synthetic
requests, independently of the older extractive dialogue/review API:

- `.dispatch(viewer, key, scene_id, source_id, expected_source_revision,
  addressed_to='gm'|'handler')` always sends the accepted own source message to the
  GM first. A Handler target then gets a separate request containing the original
  question and actual appointed Handler's knowledge. Returns separate `gm` and
  optional `handler` saved exchanges; the GM result survives a Handler failure.
- `.respond(..., route, expected_source_revision)` is the per-role service seam.
  Separate stable subkeys make retries return saved outcomes without new provider
  calls. `.get(viewer, scene_id, exchange_id)` reopens only the original owner's
  result under current membership, role and consent. No administrator override.
- GM input includes full canonical campaign state, campaign mission/off-duty/work
  records, scene actions/receipts/choices, all current scene reference knowledge
  and the latest 100 source-history entries, with an explicit omitted-entry count.
  Canonical state and current knowledge remain available outside that raw-history
  window; no summarised memory of omitted dialogue is claimed. This server-only input is never saved in the reply,
  returned to the player or forwarded to the Handler. Credentials are outside it.
- Handler input includes its role-bound source references and the original
  question, with other actors' knowledge and hidden dependency IDs removed. Actual
  appointment, controller, living role, scene/cast membership and consent are
  checked. No forged Handler principal is used to build its context.
- Replies carry `route`, `disposition`, `text`, `source_refs`, optional `play_id`,
  and `application='blocked'`. Objective/scope/status answers cite known sources;
  unknowns ask for clarification. Mechanics requests produce a typed Play-workflow
  referral, including `keep_your_head` when recognised. They do not execute a Play.
  The synthetic GM reveals only recipient-known references despite broader input.

`record(..., topic='general'|'objective'|'scope'|'status')` supports the bounded
synthetic lookup. Old references default to general; old general command hashes
remain compatible. No new database migration is needed. Providers are separate
protocols with strict request schemas; this synthetic-only service accepts only
the exact permitted deterministic response. It is not a real-model integration.

Direct requests bypass the 120-second routine review wait. A saved GM exchange
excludes only its exact source revision from routine pending work and invalidates
an in-flight old batch; other pending messages remain. Edits become eligible again.
GM history still contains directly handled inputs. Source or safety changes during
generation reject the new reply; privacy/campaign state never comes from a browser.

The later UI should submit an explicit GM/Handler target, retain separate role
labels, and render the returned reply IDs/citations with escaped text. GM routing
metadata need not be presented as a second in-fiction speaker. Show Play referrals
as links to actual engine choices, never as a completed roll or spent resource.
No UI implementation is needed to run this engine trial.

The trial runner now writes `var/gm-handler-conversation.json` and `.html`: 50
scripted Pilot messages, 50 engine GM replies and 40 engine Handler replies across
five narrative settings. Background facts are fixture setup, not scripted Handler
lines. Settings imply no actual travel; these are five chapters of one synthetic
conversation, not five 100-message scenes. External tokens/cost and dice rolls: 0.
See [actual evidence](../reports/P2_GM_HANDLER_ROUTING.md). Freeform personas,
automatic mission commitments, orders, live publication and paid calls remain open.

## Engine-selected Handler interventions in long scenes

Use `process_message(viewer, key, scene_id, source_id, expected_source_revision)`
for unlabelled conversation. It processes the GM route, then persists a separate
role-scoped `HandlerDecision` before generating any Handler reply. `WAIT` produces
no Handler generation call; `RESPOND` binds the reply to the saved decision and
current context. Source/scope changes make an unused decision stale. Retries reuse
saved silent decisions and replies. Existing explicit `dispatch`/`respond` APIs
remain low-level direct-request seams; they are not this observation policy.

The local deterministic policy supports direct Handler questions and one narrow
unsolicited correction: a stated forced-entry plan contradicting the Handler's
known explicit scope. Mere mentions, ordinary Pilot conversation, negated plans
and explicit GM requests yield WAIT. The warning quotes its known source and
chooses no player action or outcome. This is synthetic need detection, not general
roleplay reasoning, live observation or autonomous publication.

Run `.venv/bin/python tools/run_handler_scene_trials.py` for two independent
disposable scenes, each with 100 scripted Pilot inputs. Fixtures contain no Handler
lines, route selectors, expected-reply labels or reply quota. Actual Handler
messages are appended only after a saved RESPOND decision. The output is
`var/handler-long-scenes/index.html`, with highlighted interventions, trigger/input
numbers, reasons and citations; `.json` files include all silence decisions and
separate GM diagnostics. `transcripts.txt` provides a plain-text transcript.

## Actual Play workflows and visible GM interventions

Run `.venv/bin/python tools/run_handler_scene_trials.py --plays` to exercise three
actual native Keep Your Head workflows inside each 100-input scene. Results are
under `var/gm-handler-play-scenes/`. The GM and optional Handler generators remain
deterministic, with no response quota or real model calls. The test driver supplies
explicit actor/controller choices and deterministic test dice through the existing
native services; no Director prose is treated as permission to execute a Play.

`ConversationReply.gm_decision` marks `RESPOND` versus `WAIT` for private GM reviews.
Supported visible reasons are explicit GM request, named Keep request, proposed
forced-entry adjudication and proved completion. Ambient private reviews remain
saved diagnostics. Handler replies cannot carry a GM decision. The transcript
shows only marked GM interventions, not an unrelated clarification after every line.

`DirectorConversationService.review_play(viewer, key, scene_id, action_id)` creates
an owner-private GM readback only after native ordinary Keep is actually complete.
It reuses the same source proof as observation: original participants/actor,
no unsupported child/playbook source, no pending choices/required work, original
receipt, response event and canonical history. Final proof and saved readback commit
in one transaction. `get_play_review(viewer, scene_id, id)` reopens the original
actor's saved result. Other owners and administrators receive no ownership bypass.
The native receipt/total/tier are whitelisted; private Handler outcome text, raw
state and actor choices are not copied. Retries roll no dice and apply no effects.
Only the exact handled completion revision is excluded from routine pending work.

Each demonstration follows real scene lock → one 2d6 receipt → each participant's
Tag response → Pilot's printed trait/Tag choices → original Handler's mandatory
enough/not-enough ruling → committed result and lock release → GM readback.
The engine blocks readback while that required Handler answer remains outstanding.
Gold transcript entries are scripted test-owner choices, including those required
Handler rulings; teal Handler dialogue is separately generated after its need gate.
Blue entries are GM interventions, and grey entries are actual workflow stages.

These runs deliberately change disposable mechanical state and create real test
Tags on high-tier results. Each consumes exactly three test rolls, all Heat choices
are 0, and no live campaign changes. A low/mid/high tier alone does not establish
mission success, access or cancellation of another Play. Other Play completion
families, general automatic Play consumption and live publication remain unsupported.

## Contextual GM rulings before confirmation

`DirectorAdjudicationService(conversation, provider=None).adjudicate(viewer, key,
scene_id, source_id, source_revision, action_id)` now produces a private GM proposal
after actual Keep actor choices, before its pending original Handler confirmation.
It binds the accepted original Pilot's message to the actual native Play context,
receipt, action revision, positive/negative traits and pending choice ID. Foreign
actors, substituted context, unresolved actor choices, unsafe/stale contexts and
unsupported child/playbook sources reject. Provider generation runs outside the
writer lock; request/context proof is rechecked before saving. `.get(viewer,
scene_id, id)` reopens only that owner's saved proposal. No raw GM context is saved
or sent to the separate Handler dialogue provider.

The common response contains `verdict`, `enough`, the attempted goal, reasoning,
proposed narration, citations and `application='proposal_only'`. A resolved GM
verdict must have a matching enough value. Unknown goals or unestablished relevant
traits return `needs_clarification`; another Play returns `requires_play_adapter`.
Keep's binary enough judgment is never imposed on a different printed Play.

The local policy is an explicitly bounded simulation of discretionary GM judgment:
deliberate control matters for stated focus/precision/composure tasks, and toughness
matters for stated cold/endurance tasks. These interpretations are not printed
automatic trait-success rules. A positive relevant trait can be enough; its actual
negation can prevent the goal; a trait neither selected nor negated is unknown.
The provider does not infer a new trait, injury, punishment, expenditure or PC action.
Broad natural-language reasoning and other Play-specific outcome adapters remain open.

The `--plays` driver now copies the actual declaration into native `PlayInput.context`
and asks the GM to assess its goal after the actual choices. The fixed fixture flag
`tier != low` has been removed. The Handler test controller confirms the computed
GM ruling through its own actual `handler_keep` choice; no generator impersonates
that controller or bypasses the native commit gate. A successful proposal alone is
not a committed outcome. General automatic/live proposal consumption is not installed.

Completed GM readback recognises a confirmed proposal only when the original
source revision/context, original pending choice response, actual enough value and
submitted GM reasoning/narration agree. It copies that previously safe proposal,
not arbitrary private Handler outcome text. A different owner ruling retains the
ordinary receipt-only readback. Old saved proposals remain history, not authority
to apply an outdated ruling; a later UI must obtain a fresh proposal for changed context.

The two updated 100-input scenes each demonstrate **5/low → goal success**,
**9/mid → goal success**, and **12/high → goal failure** from actual traits/context.
Separate focused native tests keep the total at 9 and vary traits, then keep the
traits and vary the goal. This distinguishes contextual judgment from tier-based
success. No real model calls, paid inference, deployment or live campaign changes.

## Broader experiment and accepted AI-GM direction

The owner approves engine-verified context and actual choices → contextual AI-GM
proposal → engine validation/recording under configured authority, with a separate
scoped Handler view. This is not an AI confirming a deterministic engine judgment.
The current provider remains a local stand-in; no paid calls are authorised.

Run `.venv/bin/python tools/audit_director_rulings.py` for the new 40-case,
five-native-Play experiment. The [review](../reports/P2_DIRECTOR_RULING_AUDIT.md)
records the actual findings and prioritised next work. The local evaluator was
left unchanged: it produced 10 poorly grounded Keep judgments, two safe coverage
gaps and multiple unsupported Play/lineage responses. Native guards, actual rolls
and scoped Handler projections were exercised separately. This evidence does not
validate a real AI GM or imply a complete autonomous-live candidate.

Prepare explicit goals/stakes/prerequisites and evidence-bound outcome proposals,
then add each Play's specific adapter and completion lineage. Preserve deterministic
authority/privacy/choice/cost/replay checks; the current exact-template equality
guard must be replaced with actual validation before a real provider can be used.
Do not forward full GM context to the Handler or treat narration as an authorised
arbitrary mechanical/world command. UI integration remains intentionally deferred.

## Local trial console before UI work

A disposable, engine-only trial is now runnable:

```bash
.venv/bin/python tools/director_trial_console.py
.venv/bin/python tools/director_trial_console.py --interactive
```

Default runs a bounded demonstration; interactive mode accepts synthetic scene
text and `/wait`, `/npc`, `/approve`, `/publish`, `/status`, `/quit`. Here `/publish`
means the synthetic projection in the disposable campaign, with no Discord or
network delivery. The console uses the existing synthetic world, actor, venue and
release-test fixtures; it creates no real campaign approval. Temporary state is
removed on exit and the original environment is restored. External tokens/cost:0.
This development console requires pinned dev dependencies; it is not a bot startup,
production installer, new campaign database authority or general AI model emulator.

The successful demonstrated flow is source submission → explicit NPC reference
knowledge → quiet batch/WAIT → actual-role extractive draft → controller approval
→ source-proved contribution → de-identified participant refresh → idle queue.
This makes a bounded synthetic shadow/report trial usable before the Activity.
It does not certify the complete Director or authorize autonomous real gameplay.
