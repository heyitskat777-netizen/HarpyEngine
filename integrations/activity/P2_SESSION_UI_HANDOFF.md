# Consolidated Activity session UI handoff

The subsequent [delegated model review](../../reports/P2_TERRA_MODEL_REVIEW.md)
exposes additional real-provider contract gaps: natural Handler prose is still
rejected by the default synthetic transport; actor names/aliases, first-report
testimony and machine-readable validation requirements need work. Do not treat
fixture passes as permission to connect an arbitrary free-form model. Unordered
policy-set fingerprints are now canonical across process restarts; reopen old
unconfirmed packets when upgrading the source.

This is the engine-first implementation brief for the Activity project. It joins
the existing [native Activity ports](INTEGRATION_HANDOFF.md) and
[AI-assistance contracts](../ai_assistance/INTEGRATION_HANDOFF.md).
The source bundle remains comparison input; this document does not install an
HTTP route, frontend, authentication flow, model, worker or live policy.

## Session surfaces

| Surface | Read contract | Required controls and visibility |
|---|---|---|
| Scene | `DirectorSessionService.submit`, `contributions` | Persist the full original command/key; render separate GM and Handler replies. WAIT is silence. Only approved participant contributions enter the shared transcript. Private GM packets/reasoning stay out. |
| Scene work | `.work(viewer, scene, gm=False)` | Render original pending choices, declarations, proposals and their actual owners. A subject of a decision is not necessarily its decision owner. GM scope requires native authorization. |
| Campaign work | `.campaign_work(viewer, scene, period_id=None)` | Show mission controls, current/selected Off-Duty progress and required campaign work. This is a recipient-specific OOC dashboard, not a Handler persona prompt. Keep private scenes and personal sheet choices in their native recipient projection. |
| GM desk | `.decision_context`, `GMOutcomeService.open/packet/propose` | Bind the actual native source/receipt, context and declared goal. Show typed outcome fields, are/are-not assessments for Keep and unresolved prerequisites. GM visibility cannot confirm another source owner's choice. |
| Owner review | `GMOutcomeService.owner_review/confirm` and native choice services | Present intended effects/disclosures to the actual decision owner; preserve personal selections and acknowledgements. Reopen stale work; never auto-fill consent or clone an old confirmation onto a new source. |
| Handler comms | Existing engine RESPOND/WAIT gate and narrow Handler request | Only explicit Handler-known references feed fictional speech. `briefing`, `tactical`, `debrief` can queue announcements. Successful delivery suppresses the same root update for the same Handler/roster across handoffs; a failed generation remains retryable. |
| Continuity | `SceneContinuityService.preview/carry` | Close the original native scene, join/configure/consent to the next scene, then select references and dependencies. Use both actual revisions. Only the same roster is supported. Preserve known-by actors, claims and root provenance. |
| Blocked memory | `DirectorContextService.archive_review/archive` | Metadata-only IDs/dependencies permit retiring blocked references. Require an explicit reason and dependency-closed selection. Withdrawal of original consent blocks use of its carried text; never restore a cached prompt to get around that block. |
| Knowledge acquisition | `.work(..., gm=True).knowledge_sources`, `session.knowledge` | Review new messages/approved readbacks through a GM-only source packet. A trusted injected GM provider proposes quoted facts and actual recipients; the engine validates before creating references. Keep private proposals/reasoning outside role prompts and shared storage. |

## Fictional channels and knowledge acquisition

`AppendSceneInput.fictional_channel` is `scene` (legacy/default scene speech),
`private` (unreported narration/perception) or `comms` (an explicit report).
Set this before routing the message: private text is removed from the Handler's
current question as well as excluded from its knowledge. The GM can still read
the source. Merely filtering stored references does not protect a prompt that
already contains the private current message. Editing cannot change channels;
sharing a private observation requires a separate comms message.

This is a fictional hearing boundary, not a Discord DM or new OOC access rule.
The existing synthetic scene audience and consent requirements remain in force.
Do not infer a private channel from styling alone, and do not assume a later GM
proposal can undo disclosure. Add an explicit narration/comms control to the UI.

The service is available as `DirectorSessionService.knowledge`:

```text
pending(gm, scene) -> unreviewed source_id/source_revision metadata
open(gm, key, scene, source_id) -> request ID
packet(gm, scene, request_id) -> private KnowledgePacket
propose(gm, key, scene, request_id, KnowledgeProposal) -> proposal ID
generate(gm, key, scene, request_id, injected_provider) -> proposal ID
private(gm, scene, proposal_id) -> private GM proposal/reasoning and current status
confirm(gm, key, scene, proposal_id) -> new reference IDs, effects_applied=false
acquire(gm, key, scene, source_id, injected_provider) -> complete trusted GM path
```

`generate` calls a provider outside the transaction and saves a validated private
proposal. `acquire` performs open/generate/confirm with stable derived keys; retries
reuse the original generated result and accepted references. No provider is
installed or scheduled by default, and the browser must not choose credentials,
GM identity or a paid provider. Human review can use the separate steps.

A trusted synthetic server can configure `DirectorSessionService` with both
`knowledge_provider` and `knowledge_gm`. Then `submit` saves the input, processes
its GM acquisition proposal and only afterwards routes the conversation to the
GM/Handler. A failure resumes under the original command key, including when
knowledge was accepted before a later Handler failure. Omitting both arguments
preserves the provider-free path; supplying only one is rejected. These are server
configuration values, not fields in the user's message or browser permissions.
Background processing must retain the existing selective-observer eligibility;
listing unreviewed source metadata does not install a worker or generation schedule.

`KnowledgeProposal` contains a request ID, private reasoning and up to ten updates.
Each update has a `basis`, exact `quote`, actual `ActorRef` recipients, optional
`prior_reference` and topic. Quote only the intended fact, not its source's whole
private narration. The accepted reference exposes that quote and permitted
provenance, excluding unrelated asides and private reasoning.

- **Perception:** a message can establish its own actor's perception claim. It
  cannot silently give that claim to the Handler or another Pilot.
- **Report:** an explicit comms source must quote a real reference known to its
  original speaker. Only selected current actors receive it. The new reference
  remains a reported claim; the speaker's private prerequisite stays hidden from
  recipients who do not know it.
- **Outcome:** confirmed knowledge requires an actual approved native outcome
  readback. Message prose cannot promote an enemy/location or success into canon.

The GM provider judges semantic interpretation, hearing plausibility and which
source fragments matter. The engine proves source, exact quote, actor identity,
scope, known speaker content, revisions and consent. It does not simulate sight
lines, classify arbitrary natural language by itself or treat OOC scene membership
as proof that every character perceived an event. Unsupported sources or uncertain
acquisition remain GM review work.

Knowledge remains in append-only records across restarts and explicit scene
handoffs. Corrections invalidate stale prompt material until reconciliation;
metadata-only retirement preserves history rather than asserting fictional
forgetting. Native mechanics and player/Handler choice ownership remain separate.

## Campaign dashboard contract

`campaign_work(viewer, scene, *, period_id=None)` returns:

```text
scene_id
missions             # MissionControlService.view(viewer), including offers/desk
current_period_id    # null when no unfinished native period exists
period               # CycleService.review(viewer, selected period), or null
required_work        # native unresolved rows owned by OR concerning this viewer
scope = recipient_ooc
application = native_services_only
```

Passing `period_id` reopens the selected native period, including a completed one;
it grants no new membership or decision authority. `required_work` includes IDs,
revisions, mission/period links, kind, owner, subject and state, without raw private
body text. Compare `owner_id` with the authenticated viewer before offering an
input; subjects may need a read-only status instead. Native forms still prove
effective author, current source and permissions when opened/committed.

The dashboard is a read view assembled from native projections, not an atomic
reservation. Every write must reopen its actual native form and supply its exact
expected revisions. Keep the existing direct native controls available outside
optional Director observation. The assisted dashboard additionally requires the
current synthetic scene membership, consent and safety guard.

## Native mission and Off-Duty sequence

1. **Invite and dispatch.** Use native mission offer/individual response/start.
   Render Handler `actions`/`blocked` and desk capability fields from
   `MissionControlService`; do not infer eligibility from phases or counts.
   Each Pilot answers their own invitation. Offering and dispatching are distinct.
2. **Resolve scene work.** Native Plays, costs, actual owners, GM proposals and
   original-owner confirmations remain independent of conversation. A narrated
   success cannot complete the native action or mission.
3. **Debrief and rewards.** The Handler records native success/failure/debrief.
   `rewards_committed` does not mean every consequence is resolved. The rehearsal's
   successful mission still creates required Dog discipline; show that work before
   allowing completion. Use `PunishmentService.get/apply` under its actual owner,
   with consultations/follow-ups where required. Do not infer consent from the
   subject's identity or replace a typed effect with a GM acknowledgement.
4. **Prepare Off-Duty.** `OffDutyService.begin` creates the actual preparing period.
   Offering/dispatching another mission remains blocked. Show the real
   `off_duty_strain_start` task and use `StrainService.work/prepare` for its factual
   review. Scenario configuration is a trusted initial campaign operation, not a
   client reset shortcut.
5. **Roll and apply Strain.** Native `roll` saves one die; `choose` selects its
   actual column. `EffectService.get/apply` resolves the source-specific effect
   and required follow-ups. A saved column alone is not completion. Never expose
   synthetic injected die faces as production input or provide a generic skip.
6. **Activate and recover.** `CycleService.activate` checks actual preparation.
   Each Pilot makes their real Go Off-Duty Play. Use the native result's allowed
   scene choices: the routine tier's barracks/mess/hangar options differ from the
   high tier's city/office options. Frame rewards retain their actual source
   conditions and owners. Resolve scene acknowledgements separately for every
   participant before `recover`; one account cannot acknowledge for another.
7. **Handler scene, Status, world.** Use native Handler scene, individual
   acknowledgements and `review_status`. A later native state change can invalidate
   the review. `finish` applies actual directed world movement/follow-ups and only
   completes when all required work is resolved. Show pending work rather than a
   progress bar that implies it can be waived.
8. **Next scene/mission.** When the period is genuinely complete, native mission
   controls become eligible again. Carry selected knowledge through the explicit
   scene handoff; new mission acceptance and dispatch still require their own
   native commands. Preserve the changed Status order and original characters.

## Retry, privacy and acceptance

- Authenticate the actual Discord Activity session server-side. Persona switching
  in the local console is a fixture, not an authentication implementation. Keep
  platform roles, human decision owners and fictional actors separate.
- Save the original payload, revisions and durable command key before submission.
  Retry that exact command after interruption. Refreshing revisions changes intent
  and requires a fresh review/key; it is not an idempotent retry.
- Never copy `campaign_work`, a GM packet, canonical state or private native scene
  summaries into Handler context or shared Activity storage. Explicit knowledge
  assignment is a separate, authorized operation. Broad GM access is not a
  disclosure rule for participant-facing prose.
- Keep current default-empty specialist release scopes and GM-discretion table
  policy boundaries. Unknown source kinds/branches retain their native review or
  release blocker. This handoff does not enable unimplemented rules.
- Implement one browser acceptance pass covering actual login, per-user work,
  wrong-owner denial, reconnect/retry, safety/consent withdrawal, private scenes,
  one typed GM confirmation, one Handler update and the native campaign sequence.
  Then run a short facilitated human session for ruling quality and pacing.

The engine rehearsal passes on a declared non-Void starting fixture with three
specific low-severity Strain effects. It completes the first mission and period,
dispatches a second mission and resolves a Play there. It does not certify all
Strain branches, all-type Activity forms, real-model quality or live delivery.
See [current results](../../reports/P2_MISSION_CYCLE.md) for exact evidence.
