# Consolidated Activity session UI handoff

The [model-contract revision](../../reports/P2_MODEL_CONTRACT_REVISION.md) addresses
the earlier delegated review with source-filtered hearing, testimony/paraphrase
claims, native actor names, structured feedback and private reviewed Handler
drafts. The default transport remains synthetic; a trusted server must explicitly
configure reviewed mode. Reopen old unconfirmed packets when upgrading source.
These contracts do not install a provider or authorize external model spending.
The [reviewed worldbuilding workflow](../../reports/P2_WORLDBUILDING.md) adds
native-backed setting details, owned agendas, unresolved complications and ordinary
NPC/faction introductions, with explicit later recipient disclosures.

This is the engine-first implementation brief for the Activity project. It joins
the existing [native Activity ports](INTEGRATION_HANDOFF.md) and
[AI-assistance contracts](../ai_assistance/INTEGRATION_HANDOFF.md).
The source bundle remains comparison input; this document does not install an
HTTP route, frontend, authentication flow, model, worker or live policy.

The [Living Campaign work package](../../docs/work_orders/P2_LIVING_CAMPAIGN.md)
adds controller-confirmed dossiers, private Front attention and reviewed NPC
reactions. See [verification and limits](../../reports/P2_LIVING_CAMPAIGN.md).

## Session surfaces

| Surface | Read contract | Required controls and visibility |
|---|---|---|
| Scene | `DirectorSessionService.submit`, `contributions` | Persist the full original command/key; render separate GM and Handler replies. WAIT is silence. Only approved participant contributions enter the shared transcript. Private GM packets/reasoning stay out. |
| Scene work | `.work(viewer, scene, gm=False)` | Render original pending choices, declarations, proposals, `response_requests` and their actual owners. Target answers are separate from native ruling confirmations. A subject of a decision is not necessarily its decision owner. GM scope requires native authorization. |
| Campaign work | `.campaign_work(viewer, scene, period_id=None)` | Show mission controls, current/selected Off-Duty progress and required campaign work. This is a recipient-specific OOC dashboard, not a Handler persona prompt. Keep private scenes and personal sheet choices in their native recipient projection. |
| GM desk | `.decision_context`, `GMOutcomeService.open/packet/propose/feedback` | Bind the actual native source/receipt, context, declared goal and response ownership. Show typed outcome fields, are/are-not assessments for Keep and unresolved prerequisites. GM visibility cannot confirm another source owner's choice. |
| Owner review | `GMOutcomeService.owner_review/confirm` and native choice services | Present intended effects/disclosures to the actual decision owner; preserve personal selections and acknowledgements. Reopen stale work; never auto-fill consent or clone an old confirmation onto a new source. |
| Handler comms | Engine RESPOND/WAIT gate, narrow request and reviewed draft APIs below | Only established speech and Handler-known references feed fictional speech. Reviewed replies stay private until GM approval. `briefing`, `tactical`, `debrief` can queue announcements. Approved exchanges suppress the same root update for the same Handler/roster across handoffs; a failed generation remains retryable. |
| Continuity | `SceneContinuityService.preview/carry` | Close the original native scene, join/configure/consent to the next scene, then select references and dependencies. Use both actual revisions. Only the same roster is supported. Preserve known-by actors, claims and root provenance. |
| Blocked memory | `DirectorContextService.archive_review/archive` | Metadata-only IDs/dependencies permit retiring blocked references. Require an explicit reason and dependency-closed selection. Withdrawal of original consent blocks use of its carried text; never restore a cached prompt to get around that block. |
| Knowledge acquisition | `.work(..., gm=True).knowledge_sources`, `session.knowledge` | Review new messages/approved readbacks through a GM-only source packet. A trusted injected GM provider proposes quoted facts and actual recipients; the engine validates before creating references. Keep private proposals/reasoning outside role prompts and shared storage. |
| Worldbuilding | `session.worldbuilding`, `.work(...).worldbuilding` | GM privately proposes/reviews; actual native world owner separately confirms. Raw commitments remain outside fictional role knowledge. Selected exact disclosures create scoped established references. |
| Character dossiers | `session.dossiers` | Controller-confirmed versioned persona/state; separate GM notes. Public personnel is an explicit allowlist with native identity visibility. |
| Campaign pressures | `session.fronts` | GM-only Fronts and manual world-owner time review. Actors receive flat already-known fragments. Ready clocks/deadlines request attention without applying consequences. |
| NPC agency | `session.reactions` / `DirectorDialogueService.reactions` | Role-only packets, private proposals and actual controller review. WAIT is silence. Scene offers preserve player choice; action requests link existing native work. |

## Fictional channels and knowledge acquisition

`AppendSceneInput.fictional_channel` accepts `scene` (legacy/default), `private`,
`comms`, `mixed` and `unclassified`. Add explicit narration/comms controls; use
mixed or unclassified for prose combining actions, thoughts and dialogue. In
**reviewed mode**, scene/mixed/unclassified input supplies the Handler only exact
speech quotes accepted by the GM for that listener. Before classification the
Handler gets a neutral update, not the raw message. Private input can never be
disclosed by a proposal. The GM can still read the original source.

**Comms means explicit public scene speech.** Its entire message may enter the
Handler's current question, even if another character is named. It is not a
private radio or Discord DM implementation. For selective hearing, use a
mixed/unclassified source with explicit disclosure recipients. Never put private
asides in a comms input. Editing cannot change channels; sharing an existing
private observation requires a new message.

This is a fictional hearing boundary, not a new OOC access rule. Existing scene
audience and consent requirements remain in force. Styling alone is not a
privacy boundary. The legacy synthetic transport retains its earlier handling
of ordinary scene speech; opt into reviewed mode before using mixed prose with
a natural Handler provider.

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
feedback(gm, scene, request_id, raw_proposal) -> {valid, errors: [{code, field, message}]}
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

`KnowledgePacket.actor_directory` supplies actual `ActorRef`, native name,
controller and available native aliases. Resolve labels to those IDs; never
authorize by a name or invent console aliases. `accepted_disclosures` records
already accepted speech/listeners for that source revision.

`KnowledgeProposal` contains a request ID, private reasoning, up to ten updates
and optional `disclosures`. Each disclosure selects a unique exact source quote
and actual listeners. Each update has a `basis`, exact current-source `quote`,
actual `ActorRef` recipients, conditional `prior_reference` and topic. The engine
checks source, revisions and recipients; the GM judges whether a quote was
actually spoken and heard. Quote only the intended fact. Accepted references
exclude unrelated asides and private reasoning.

- **Perception:** a message can establish its own actor's perception claim. It
  cannot silently give that claim to the Handler or another Pilot.
- **Report:** an explicit comms source must quote a real reference known to its
  original speaker. Only selected current actors receive it. The new reference
  remains a reported claim; the speaker's private prerequisite stays hidden from
  recipients who do not know it.
- **Testimony:** a new spoken claim needs no earlier reference. It requires comms
  or an accepted disclosure to each recipient. Preserve attribution, lies,
  uncertainty and negation; it is a reported claim, not canonical truth.
- **Paraphrase:** current spoken words link to a real speaker-known prior
  reference, without requiring verbatim equality. Semantic equivalence remains
  GM judgment. Recipients receive a claim with `reported_by` identifying its
  speaker, not the hidden prerequisite text.
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

`Acquisition.relations` optionally links current accounts using
`KnowledgeRelation(kind="competes_with"|"corrects", reference_id=...)`. Accepted
references retain those links, original authors and claim/outcome classification.
Neither relation erases the earlier statement or establishes which account is
true. A native approved outcome can correct a claim; testimony remains testimony.
Actor/Handler projections include a link only when that actor knows both accounts,
and remove hidden dependency IDs as well. Carry both endpoints across scene
handoffs; the service remaps validated roots. Archival must be dependency-closed.
Display these as attributed accounts/corrections, not automatic truth labels.

## Reviewed Handler and response ownership

Trusted server configuration may inject a Handler provider into
`DirectorConversationService(context, handler=provider, handler_mode="reviewed")`
and pass that conversation service into the session. The default is synthetic;
the browser cannot select a provider, mode or GM authority. Reviewed session
defaults also require explicit Keep response scope in `TaskFrame`.

The engine must persist RESPOND before invoking the provider. WAIT remains
silence. Reviewed replies use `provider="reviewed-handler-v1"`, real scoped
`source_refs`, and no GM/Play decision fields. Factual `answer` replies need
citations; unknown information uses `clarification`. Valid citations do not
prove that prose follows from them, so accepted generation creates a private
draft with `reply=null`, `status="awaiting_gm_review"`.

```text
conversation.pending_handler(gm, scene) -> draft metadata
session.work(gm, scene, gm=True).handler_drafts -> same discovery metadata
conversation.private_handler(gm, scene, draft_id) -> private request/reply/status
conversation.feedback_handler(gm, scene, source_id, raw_reply) -> structured errors
conversation.review_handler(gm, key, scene, draft_id, "approve"|"reject", reason)
conversation.get(original_sender, scene, draft_id) -> approved private exchange or no reply
```

GM review checks grounding, scope and disclosures. Approval rechecks the original
actor/source and current context, creates one private exchange and applies no
mechanics. Rejection releases no prose. Neither approval nor generation posts a
Discord message or inserts a shared scene contribution. UI delivery must respect
the existing audience/approval path; do not broadcast private exchanges directly.

For strict ordinary Keep outcomes, trusted facilitator frames declare
`response_scope="self"|"other"|"unresolved"`. `other` additionally requires the
actual `response_target: ActorRef`; the engine derives its controller from native
state and casting. Unresolved authority permits clarification only. Another
Pilot's agreement, feelings or voluntary action cannot be supplied by a GM
verdict; this adapter holds for their response. Explicitly cast NPCs are eligible
only under their actual controller/source authority. A goal to deliver a calm
explanation can be self-scoped; a goal requiring the listener to become calm
cannot silently use that scope. This declaration is a trusted semantic judgment,
not automatic pronoun or intent detection. Legacy outcome services retain their
default compatibility mode; integrations must enable `require_response_scope=True`
if constructing them outside the reviewed session defaults.

GM and knowledge feedback APIs are private, read-only diagnostics. Keep retries
linked to their original failed proposal; do not replace first-pass evidence.
Refresh stale requests rather than changing IDs on an old confirmation.

## Controller response handoff

`session.responses` (also `outcomes.responses`) supports an ordinary Keep goal
whose outcome needs another actor's voluntary response:

```text
request(gm, key, scene, outcome_request_id, question) -> response request ID
pending(viewer, scene, gm=False) -> actual controller's pending metadata
get(viewer, scene, request_id, gm=False) -> private question/own answer/status
answer(controller, key, scene, request_id, "accept"|"decline"|"clarify", text)
resume(gm, key, scene, request_id) -> new source-bound GM outcome request
```

The GM explicitly selects the question to disclose; private stakes, assessments
and canonical context are not forwarded. Only the frozen actual target controller
can answer. The answer is private adjudication evidence, not a shared scene entry,
fictional Handler knowledge, consent to unrelated actions or a mechanical effect.
GM work lists answered requests as `answered_resume_required`. Resuming binds the
new frame's `response_request` to the exact original attempt, target and answer.
The proposal must cite `target_response`; refusal cannot become a successful
voluntary agreement, and clarification cannot authorize an assumed response.
The actual native choice owner still reviews/confirms the outcome separately.

The handoff binds native choices/receipts, actors/casting, policy, safety and
consent generation. Unrelated transcript additions do not revoke a question;
withdrawal followed by renewed consent does not revive it. Answer retries reuse
the saved record and do not reroll. A changed attempt needs a new question.
Scope is bounded to supported ordinary Keep consumers; printed personal-choice
services retain their existing independent ownership and APIs.
The GM must still check that the disclosed question matches the framed goal.
One target is supported per handoff; multi-target reactions require clarification
or separately established native work, not blanket agreement from one answer.

## Reviewed response needs

The legacy response gate remains available. In reviewed mode a GM can additionally
propose a source-bound need for an indirect request or an urgent known report:

```text
conversation.open_handler_need(gm, key, scene, source_id) -> need request ID
conversation.handler_need_packet(gm, scene, request_id) -> narrow HandlerNeedPacket
conversation.propose_handler_need(gm, key, scene, request_id, HandlerNeedProposal)
conversation.generate_handler_need(gm, key, scene, request_id, injected_provider)
conversation.private_handler_need(gm, scene, proposal_id) -> private review/status
conversation.pending_handler_needs(gm, scene) -> pending metadata
conversation.review_handler_need(gm, key, scene, proposal_id, "approve"|"reject", reason)
```

`HandlerNeedProposal` uses `action=RESPOND|WAIT`,
`kind=indirect_request|urgent_known_report|no_need`, actual `source_refs`, an exact
heard `speech_quote` for indirect requests, and private reasoning. Urgent reports
must cite Handler-known references from that actual source. A hidden perception
or unrelated reference cannot justify intervention. Semantic urgency/addressing
remains GM judgment; an approved need can augment legacy WAIT but does not revoke
an existing eligible direct request/update or a GM-addressed exclusion.

A Handler-visible `corrects` relation on objective/scope/status knowledge also
qualifies as an engine update. Both linked accounts must be known to that Handler
for the relation to survive projection. Selection and delivery suppression share
the same eligible-reference definition; an approved correction is announced once.

The engine persists the final RESPOND/WAIT and rechecks the actual need before
generation and draft save. Need approval does not approve natural reply prose:
the separate private Handler draft review remains mandatory. Only approved
exchanges count as delivered for suppression. A new genuine repeated request can
be answered; replay of the same delivered need stays silent.

Trusted servers may pair `need_provider` and `need_gm` on DirectorSessionService.
This explicitly invokes `acquire_handler_need` (open/generate/trusted GM approve)
after knowledge acquisition and before conversation routing. Defaults remain
provider-free. The browser cannot choose that authority or enable model spending.
Use the manual steps when a human should inspect each proposed response need.

## Sensors provider input mapping

Sensor outcome packets now expose `native.answer_contract`: actual positional
answer fields with their printed questions, `consequence_required` and
`allowed_consequences`. Use `a1`, `a2`, etc. in the native selected-question order;
question names such as `foundation_destination` are not consumer field keys.
Consequence is null except when the actual native high off-list branch requires
one. Do not infer an extra consequence merely because the result is mid.
GM-private feedback returns `SENSOR_INPUT_CONTRACT` for an invalid mapping/branch.
The engine still validates the real native source and original owner; this is
input metadata, not a change to the printed Sensor outcomes.

## Reviewed worldbuilding

`DirectorSessionService.worldbuilding` provides:

```text
open(gm, key, scene, source_id) -> request ID
packet(gm, scene, request_id) -> private WorldbuildingPacket
propose(gm, key, scene, request_id, WorldbuildingProposal) -> proposal ID
generate(gm, key, scene, request_id, provider=None) -> proposal ID
feedback(gm, scene, request_id, raw_proposal) -> structured private diagnostics
private(gm, scene, proposal_id) -> packet/proposal/current review status
review(gm, key, scene, proposal_id, "approve"|"reject", reason)
owner_review(native_owner, scene, proposal_id) -> intended action without GM reasoning
confirm(native_owner, key, scene, proposal_id) -> actual world-commit ID/native result
pending(viewer, scene, gm=False) -> recipient-safe pending metadata
disclose(gm, key, scene, commit_id, quote, recipients, topic="general")
    -> world-disclosure ID, reference_ids
```

World packets bind the actual source, current canonical state/world revision,
context, scene input frontier, consent/safety and runtime authority. Requests
cannot backdate fiction or bypass pending Plays. Proposals cite `source` and
`native`, plus any actual `reference:<id>` evidence used. The provider is an
explicit trusted injection; no default model or scheduled world writer is enabled.

There are three finite action shapes:

- `DevelopmentAction(development=DevelopmentDraft(...))`: a setting `detail`,
  an owned NPC/faction `goal`, or an unresolved `complication`, attached to an
  actual location/NPC/faction. Durable lower-case `key` identifies one active
  entry; revision requires its exact active `supersedes` ID and the same kind
  and subject. All previous versions remain in canonical history.
- `NpcAction(npc=...)`: a pristine, ordinary NPC under the actual native world's
  owner. Other controllers, special source-created kinds, Director/prisoner roles,
  initial Tags/Bonds/custody and automatic reveal are outside this adapter.
- `FactionAction(faction=...)`: an ordinary native faction introduction. It cannot
  import inactive or underfunded consequence state as an introduction shortcut.

The native world subsystem still needs its existing release approval. Confirmation
uses actual WorldService consumers; this does not grant administrative GMs another
human's native world authority. GM approval and owner confirmation are separate
actions, including when one person holds both permissions. The private commit
receipt can resume after a crash following the native write without duplicating it.
`native_committed_recover_receipt` in private/pending metadata means the world
change already committed: retry confirmation of that original proposal to recover
its receipt, rather than generating a replacement NPC, faction or development.

Narrative developments do not mutate damage, costs, resources, custody, player
responses, movement or clocks. A complication records an unresolved situation;
it cannot declare the required Play complete. The GM must check whether free
prose improperly claims those effects or contradicts canon. Schema validation
cannot establish that semantic judgment. New goals on another human's NPC require
their own future workflow and remain blocked here.

**Commitment does not disclose knowledge.** `disclose` selects a unique exact quote
of at most 1,000 characters from the committed permitted text and actual current
recipient ActorRefs. Disclosure and its knowledge reference commit atomically.
Only proved `world-disclosure:` sources can become `approved_world` knowledge;
raw `world-commit:` IDs cannot. These references have classification
`established_world`, which remains distinct from `reported_claim` and native
`approved_outcome`. `Acquisition(basis="world", ...)` must quote the whole selected
disclosure and cannot widen its recipients. A character relaying it creates an
attributed claim rather than independent world authority.

Role prompts contain only the disclosed quote and scoped provenance, not the
unseen body, agenda, commit ID or private review. Same-controller NPC knowledge
survives native scene closure and explicitly cast continuity. Recipient role or
controller changes require fresh disclosure/reconciliation; old records stay in
history. Consent withdrawal blocks carried prompt use. Metadata-only pending views
remain readable when optional world capability is unavailable; writes retain
the native gates.

UI controls should present separate GM review, native owner confirmation and
explicit disclosure selection. Do not automatically post a committed world record
or treat the OOC world-owner desk as Handler persona knowledge. These are Python
service contracts; authenticated HTTP/UI ports remain a later integration task.

## Living Campaign and character agency

These are synthetic Python service contracts; no Activity routes are installed.
The existing Director scheduler owns batching and the 120-second quiet window.
`submit` does not implicitly generate NPC speech, advance Fronts or fictional time.

- `dossiers.propose(viewer,key,scene,actor,expected_version,profile,state,personnel)`
  stages a version. `review(controller,scene,id)` shows it to its original actual
  controller; `confirm(controller,key,scene,id)` appends the accepted version.
  Background and recurring forms retain the same actor ID and incarnation.
- Profile includes behavioral tendencies, voice, values, fears, contradictions,
  plausible reaction tendencies and limits. State includes goal/objective IDs,
  source-bound resource IDs, pressures, obligations, experiences, promises,
  beliefs and one-sided relationship perspectives. Perspectives remain labelled
  controller-authored; they do not establish world truth or change Bonds.
- `dossiers.gm_notes` and `.gm` are private GM surfaces. `.role_packet` returns only
  the actual controller's self context. `.personnel(viewer,scene,perspective,subject)`
  returns only the published summary/mannerisms and native visible identity.
  Controller replacement requires a complete explicitly confirmed rebase; it
  does not transfer the previous private sheet or drafts.
- `fronts.save(owner,key,scene,expected_game_revision,FrontDraft,advance=...)`
  stores an evidence-backed situation. Reference actual world developments and
  known-source IDs; keep hypotheses and possible moves visibly uncertain.
  Revisions require an actual approved native outcome or explicit fictional-time
  event; resolving requires a native outcome. One underlying native action cannot
  tick the same Front again through a different narration receipt.
- `fronts.fictional_time(owner,key,scene,expected_revision,steps,account)` is an
  explicit world-owner command. It never runs on a wall clock or between inputs.
  Due situations become ready; resources, disaster and native clocks do not change.
  `fronts.view(gm,scene)` is private. Actor mode returns flat known fragments only,
  excluding Front title, grouping, status, deadlines, clocks and hypotheses.
- `reactions.open(gm,key,scene,actor,source_id,run_id=None)` freezes the role-only
  context. Pass a real running observation claim for automatic batch work;
  omission means an explicitly requested GM review, not a second scheduler.
  `packet`/`propose`/`generate` support manual or trusted fixture proposals.
  The provider receives no GM-private Front or dossier notes and cannot submit
  executable effects. Natural speech/refusal/compromise/delay are NPC-only;
  Handler speech retains the existing engine need/review/delivery path.
- `reactions.owner_review(controller,scene,id)` excludes private model reasoning.
  `review(controller,key,scene,id,decision,reason)` records a private staged reply,
  silence, scene invitation or existing-work handoff. It never publishes speech,
  teaches listeners, resolves a Play, moves a character or executes a route.
  A successful batch review acknowledges only the existing frozen frontier;
  repeating a command cannot produce a second contribution. Rejection leaves the
  batch available for revised work. Both original and current controller must
  match; renewed casting after transfer does not expose an old private draft.
- `session.work` adds metadata-only `dossiers`, `reactions` and GM-only
  `front_attention`. Use their exact owner review APIs for prose. `reactions.ensemble`
  gives the GM current actor dossiers, review counts, latest reviewed source and
  private Fronts for considering neglected opportunities. It imposes no appearance
  quota or clock advancement.

Render proposed scenes as invitations and action requests as links to original
native workflows. Approved natural NPC drafts remain private in this version;
placing one into a shared transcript or teaching listeners requires a future
source-bound contribution/disclosure adapter. Preserve unresolved choices and
explicit consent; never implement those operations by copying cached prose.

## Sustained mission rehearsal follow-through

The [601-input synthetic campaign](../../reports/P2_SUSTAINED_CAMPAIGN.md) completes
four missions and two native Off-Duty cycles. Its pilot characters are simulated
owners of native Pilot sheets; their authored input is not a generic NPC publishing
permission. No Activity routes or real model are installed.

Two controls remain useful before a connected trial:

- An OOC intent-clarification handoff bound to the original pending Play and its
  actual actor. The GM can hold an unclear ruling, while the scene correctly blocks
  new IC input. Do not work around that lock by submitting the answer as IC speech
  or letting the model invent an intention. The current rehearsal uses explicitly
  labelled human-facilitator TaskFrame review.
- A safe persona/memory projection for the actual Handler provider. The standard
  HandlerRequest currently contains known references, question and addressed
  updates; it does not include the new self dossier. Never fill that gap with the
  GM's dossier collection or private notes.

Refresh budgets and native result choices for every new action; carrying five or
more Heat requires spending all. Refresh the original work queue after every effect:
one applied consequence may resolve overlapping tasks, and a stale task must not
be applied again. Final mission failure still follows native reward and consequence
rules; a higher roll alone does not establish a successful task or mission.

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
