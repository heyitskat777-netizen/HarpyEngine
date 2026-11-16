# Engine-first synthetic Director trial

Owner direction: finish engine work independently; UI changes are delivered later.
Model preference is tentatively GPT-6.1 Terra. No provider identity or compatibility
is asserted and no external inference/spending is authorized. All decisions here
are deterministic local fixtures, not measured or emulated model intelligence.

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
