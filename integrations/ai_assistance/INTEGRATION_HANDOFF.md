# Activity integration — synthetic assistance v1

The owner's approved [Activity-first Director design](../../docs/AI_DIRECTOR_ARCHITECTURE.md)
and [next synthetic observation work order](../../docs/work_orders/P2_DIRECTOR_OBSERVATION.md)
extend the future product plan. They preserve this delivered summary v1 API.
Synthetic-only scene submissions, self-consent and durable batching are now
implemented as the internal D1 service below. Real Activity scene APIs, Director
decisions, NPC/world contributions and general delivery remain unregistered.
Enabled NPC initiative/world proposals do not activate live mode. The observation
source is the authorized persisted Activity scene stream, not passive Discord
chat. Read the canonical design for UI and backend responsibilities before adding
those consumers; do not broaden `ReviewDraft` into a mechanical apply endpoint.

## D1 synthetic observation service — implemented, no HTTP transport

`girlframe.services.director_observation.DirectorObservationService` and strict
v1 models in `girlframe.ai.observation` implement the AI-free foundation. The
default constructor is Off; `synthetic=True` is only trusted local harness setup
against synthetic campaign fixtures, never a request field or a way to enable
actual player transcript collection. This is not a complete Activity chat store.

| Method | Exact call shape / boundary |
|---|---|
| Configure synthetic scene | `configure_scene(viewer, key, scene_id, expected_policy_revision, ObservationPolicy(...))`; configured administrator who is already a scene participant; clears prior consent and never consents for anyone |
| Own consent | `set_consent(viewer, key, scene_id, expected_policy_revision, consent=bool)`; current participant decides for that account only, including withdrawal while paused |
| Append/edit synthetic IC input | `append_scene_input(viewer, scene_id, AppendSceneInput(...)) -> InputResult`; stable key, expected scene revision, explicit `speaker: pilot|handler`, bounded text, IC/OOC classification; optional own source ID and expected source revision for an IC edit |
| Supported Play source | `observe_committed_play(scene_id, action_id) -> InputResult`; trusted internal caller; actual ordinary native Keep Your Head final event/canonical history/receipt, original actor and audience; pending/unsupported sources reject |
| Claim internal batch | `claim_review(scene_id) -> ReviewBatch | None`; trusted worker only; current policy/consent, source eligibility and one leased claim per scene |
| Complete internal synthetic review | `acknowledge_review(run_id, lease_token, success=bool) -> ReviewCompletion`; token-bound short transaction; success acknowledges only its frozen frontier, failure consumes none; changed completion conflicts |
| Safe status | `status(viewer, scene_id) -> ObservationStatus`; current participant and campaign binding; mode, own/current consent eligibility, counts, revisions and next eligible time; no message text, private results or lease tokens |

`AppendSceneInput` accepts only `schema_version`, `command_key`,
`expected_scene_revision`, `speaker`, `text` (1–1,000 characters),
`classification: ic|ooc`, optional `source_id` and `expected_source_revision`.
Identity, source author, audiences, canonical actor incarnation, clocks, ordering
and policy authority are server-owned. IC input obeys the actual scene chat lock.
OOC is ignored without retaining text or moving the quiet deadline. AI/bot/system
outputs have no input path through this human submission API.

`InputResult` is metadata only: scene/source IDs, source revision, sequence,
generation and `accepted|ignored_ooc`. Exact replay rechecks current authorization
and returns the saved result; expected revisions are first-execution conditions.
Consent is bound to the notice's policy revision as part of its semantic intent.
Each new intention needs its own key. Reopen status after an uncertain retry.

Each internal `ReviewBatch` contains campaign/scene/run IDs, lease token/expiry,
generation, scene/policy/consent/canonical revisions, bind event, a guard digest,
reason (`quiet|size|age|completed_play`), at most 20 current source revisions and
three recent-tail references. These are observed references, not fictional
knowledge grants. Worker tokens and batch bodies never belong in ordinary player
status or browser requests. Original audiences are retained; changed-audience
unread input fails with `SOURCE_SCOPE_CHANGED` and is preserved for privacy review.

The 120-second quiet/minimum routine interval, 20-message threshold and 10-minute
age are default policy settings. Size/age batches permit review only; every batch
and completion has `publication: blocked`. Leases last 120 seconds. Relevant input,
scene/source state, safety history, membership, policy or consent changes invalidate
claims. A failed or expired claim leaves unread input recoverable. Real inference,
five-way decisions and actual AI `WAIT` are not implemented by acknowledgement.

Three tables are added to the existing store by migration `0022`; applying that
migration to a real campaign remains a separate operational step. No worker or
source listener is started. The trusted engine-event consumer must explicitly
call the supported source adapter. Broader Play/child families, real retention/
redaction, fictional chronology/knowledge and Activity authentication/delivery
remain future work. Existing summary v1 contracts below remain unchanged.

HarpyEngine supplies a transport-neutral backend workflow and strict Python data
contracts. This handoff defines the v1 Activity adapter contract. It does not
establish HTTP routes, OAuth/session verification, a browser connection or a
new hosting framework. The Activity task must reconcile its actual backend and
client before binding these logical operations.

The supported product is a private, extractive **OOC public reference summary**.
It is a proposal for its requesting owner to approve or reject. Approval records
a review outcome only; it neither establishes fictional knowledge/canon nor
applies mechanics or publishes to Discord. Real provider calls and freeform
narration are outside this increment.

## Source and component ownership

| Component | Delivered boundary / responsibility |
|---|---|
| `girlframe.ai.contracts` | Strict schema version 1 context, generation request/response and summary proposal models; `Provider` protocol and extractive output validation |
| `girlframe.ai.activity` | Version 1 typed Activity inputs and context, mutation, record and refresh envelopes |
| `girlframe.ai.context` | Pure field allowlist over already authorized public `CharacterSheetDocument` projections |
| `girlframe.ai.synthetic` | `SyntheticProvider`, deterministic local generation with no network, credentials or paid model |
| `girlframe.services.ai_assistance` | Campaign/role/owner authorization, expected revisions, durable request/generation/review records and command-key replay in the existing campaign store |
| Activity backend — pending handoff | Server-verified Discord sessions, current guild/role verification, CSRF/session transport, private HTTP response handling and calls to the engine service |
| Activity frontend — separate task | Context preview, explicit Request/Generate/Approve/Reject controls, private outcome refresh and current nickname display |

Reuse the Activity's actual server framework when known. Do not create a second
campaign database, browser SQL, a browser provider client or a second SQLite
copy. A remote UI requires an authenticated adapter hosted with the authoritative
engine; the character-sheet file exchange remains a separate existing bridge.

## Identity and audience

The adapter creates `GuildViewer` exclusively from its verified Discord session
and current server-side guild membership/roles. Route campaign IDs select an
already configured engine store and must match that store; they do not authorize
access. Ignore or reject browser-submitted user IDs, administrator flags, role
claims, owner IDs, context facts or provider credentials as authority.

Every read, write and idempotent replay rechecks current campaign membership,
campaign/guild binding and the requested audience. Proposal retrieval and review
are private to the requesting owner; administrator access does not override that
ownership. Do not expose proposal existence through a different error for
another owner's record.

| Audience | Required authority | Context admitted in v1 |
|---|---|---|
| `player` | Current campaign/guild member | Only that user's authorized public character metadata: callsign, Girl/Frame references and sheet state |
| `gm` | Current member with configured administrator access | The same allowlisted public metadata for the permitted campaign roster |
| `handler` | Current member and current appointed Handler | Roster callsigns only; no automatic use of that account's Pilot context |

All facts have `knowledge: "ooc_reference"` and the context has
`scope: "public_reference_only"`. Public metadata is not evidence of a fictional
observation. Handler context is deliberately narrower than GM context. No private
notes, owner setup sections, private choices, raw game state/events, unobserved
secrets or Discord transcripts enter generation. Source IDs cite the existing
character projection, owner, character identity, revision and field. A missing
source stays missing; the summarizer does not fill gaps.

The builder supports up to 24 authorized character projections and 96 scalar facts.
It rejects excess context instead of silently truncating a different audience.
Current nicknames should be resolved through the application's authorized Discord
member lookup for display. Wire Discord IDs remain decimal strings; callsigns and
nicknames never become authorization or storage keys. Treat all returned strings
as text data and escape them in the UI.

## Logical v1 operations

Proposed HTTP paths use the prefix
`/v1/campaigns/{campaign_id}/assistance`. This is the proposed transport mapping
for the Activity task to reconcile and bind; these endpoints are not registered.
Use `Cache-Control: private, no-store` for all private responses and avoid logging
context/proposal bodies or session credentials.

| Operation | Proposed HTTP shape | Required input / result |
|---|---|---|
| Authorized context | `GET /context?audience=player` | Current authorized context plus its digest and campaign revision |
| Request summary | `POST /requests` | `command_key`, `expected_campaign_revision`, `audience`, `context_digest`, `task: "summary"`; returns saved `requested` proposal |
| Generate draft | `POST /proposals/{proposal_id}/generate` | `command_key`, `expected_campaign_revision`, `expected_proposal_revision`; returns saved `draft` or sanitized `failed` outcome |
| Review privately | `POST /proposals/{proposal_id}/review` | Same key/revisions plus `decision: "approve"` or `"reject"`; returns recorded outcome |
| Reopen / refresh | `GET /proposals/{proposal_id}` | Owner-authorized latest record, current campaign revision and source freshness; no generation or effects |

Every body is schema version 1 and rejects unknown authority/effect fields. The
adapter must preserve the typed contract's strict strings, integers and enum
values instead of relying on browser validation. The underlying context,
generation and proposal JSON Schemas are available from each Pydantic model's
`model_json_schema()`; JSON arrays correspond to the Python tuple fields.

`AssistanceContext` contains `schema_version`, `campaign_id`, `requester_id`,
`audience`, `campaign_revision`, `facts` and `scope`. Its Python `digest` property
is separate metadata: it is not included by `model_dump()`. The adapter must return
the server-computed digest alongside the context. The browser echoes only that
digest on request; it cannot submit or authorize replacement facts.

Each `ContextFact` contains `source_id`,
`source_kind: "public_character_projection"`, string `subject_id`,
`source_revision`, `field`, `value`, and `knowledge: "ooc_reference"`.
`GenerationRequest` contains the server-held context and `task: "summary"`.
`GenerationResponse` contains `provider: "synthetic-v1"` and a `DraftProposal`.
That proposal contains `kind: "summary"`, `text`, ordered `source_ids`, and
`application: "record_review_only"`. Context, generation and proposal envelopes
have `schema_version: 1`; facts use their enclosing context's version.

The exact Activity envelopes are implemented in `girlframe.ai.activity`:

- `ContextView`: `context`, `context_digest`.
- `RequestAssistance`: `command_key`, `expected_campaign_revision`, `audience`,
  `context_digest`, `task: "summary"`.
- `GenerateDraft`: `command_key`, `expected_campaign_revision`,
  `expected_proposal_revision`.
- `ReviewDraft`: the generation preconditions plus `decision`.
- `MutationResult`: `proposal_id`, `proposal_revision`, `status`,
  `campaign_revision`, `application: "blocked"`.
- `AssistanceView`: `record`, `campaign_revision`, `sources_current`,
  `application: "blocked"`.
- `AssistanceRecord`: `proposal_id`, `campaign_id`, string `owner_id`, `revision`,
  `status`, original `context`, optional `response` and optional `failure`.

Each envelope also contains `schema_version: 1`. Command keys contain 1–200 ASCII
letters, digits, colons, underscores or hyphens. `failure` is either null,
`PROVIDER_UNAVAILABLE` or `INVALID_RESPONSE`; no raw provider error is exposed.

Server-side invocation, after independently verifying the session and resolving
the actual configured engine store:

```python
from girlframe.ai.activity import GenerateDraft, RequestAssistance, ReviewDraft
from girlframe.services.ai_assistance import AssistanceService

service = AssistanceService(store)  # default: local SyntheticProvider
context = service.context(verified_viewer, audience="player")
requested = service.request(
    verified_viewer,
    RequestAssistance(
        command_key="assist:request:unique-intent",
        expected_campaign_revision=context.context.campaign_revision,
        audience=context.context.audience,
        context_digest=context.context_digest,
    ),
)
draft = service.generate(
    verified_viewer,
    requested.proposal_id,
    GenerateDraft(
        command_key="assist:generate:unique-intent",
        expected_campaign_revision=requested.campaign_revision,
        expected_proposal_revision=requested.proposal_revision,
    ),
)
private_view = service.get(verified_viewer, draft.proposal_id)
# Present private_view.record.response; wait for the owner's explicit review.
approved = service.review(
    verified_viewer,
    draft.proposal_id,
    ReviewDraft(
        command_key="assist:approve:unique-intent",
        expected_campaign_revision=private_view.campaign_revision,
        expected_proposal_revision=private_view.record.revision,
        decision="approve",
    ),
)
reopened = AssistanceService(store).get(verified_viewer, approved.proposal_id)
assert reopened.application == "blocked"
```

The adapter retains proposal IDs and command keys across reloads. There is no
list/search or individual historical-revision endpoint in this increment; `get`
returns the latest record. Underlying append-only history is retained privately
in the same authoritative campaign database by additive migration 0021. Applying
that migration to a live campaign is a separate operational action.

Output validation requires the exact deterministic summary over the authorized
facts and corresponding ordered source IDs. Extra mechanics/consent/application
fields or freeform provider prose fail closed. There is no user-selected provider,
prompt override, external context attachment or arbitrary action endpoint.

Generation currently holds the existing SQLite writer transaction while the
immediate synthetic provider runs. A real network provider requires a separately
reviewed worker/resumption design; do not place a slow model call in this path.

## Client workflow and concurrency

1. Fetch authorized context for one explicitly chosen audience. Display its OOC
   scope and sources; do not combine contexts across audiences or accounts.
2. On Request, create a stable command key for that single user intention and
   send the context digest and expected campaign revision. Keep the returned
   proposal ID and revisions.
3. On Generate, use a new stable key for that generation intention with current
   campaign/proposal revisions. This synthetic implementation returns a saved
   bounded outcome synchronously; it does not imply an async paid-provider job.
4. Present the saved draft and citations privately. Approval/rejection requires
   a separate explicit click and command key; generating or viewing never
   implies approval.
5. Refresh the recorded proposal after review or uncertain transport results.
   Reopen reconstructs saved state after an application restart; no old Discord
   interaction token is required.

A stable key identifies an operation, actor, campaign and semantic payload.
Retransmit the same key after an uncertain response; do not mint a new key to retry
an uncertain write. Recorded retries with the same semantic input return the prior
result without another provider invocation, proposal revision or audit effect.
Reusing a key with changed intent conflicts. The service rechecks authorization
before replay.
Expected revision fields are first-execution preconditions, excluded from the
semantic retry hash; refreshing them cannot cause another execution of a known
command. A replay's `campaign_revision` is the original receipt value, so fetch
the current private view before a subsequent new mutation.

A new write must match the expected campaign revision and proposal revision.
The service also checks the original context's sources before generation and
approval. A stale UI must refresh rather than force-write. Rejection can discard
a stale draft while paused, provided its expected current campaign and proposal
revisions still match. Terminal outcomes are immutable; start a new request for
a genuinely new summary/review intention.

The lifecycle is `requested` → `draft` → `approved` or `rejected`, with `failed`
as the generation-failure outcome. Records and review decisions are append-only
revisions. Provider exceptions/malformed output produce only safe failure codes,
never raw exception text or invented summaries. Manual engine operation remains
available independently of this workflow. A rejected or failed record remains
reopenable by its owner under current authorization. Failed generation is terminal
at proposal revision 2; an explicit new request is required to try again.

Application remains explicitly blocked after approval. A future mechanical
consumer must call the existing source-backed engine operations with their real
actor, costs, choices, consent, release gates, revisions and command keys. This
review record supplies none of that authority.

## Recommended transport errors

These are adapter mappings; the service does not select an HTTP framework.
Do not return raw Python/Pydantic exceptions, private input values, SQL or
provider error bodies.

| HTTP status | Meaning / client action |
|---|---|
| `400` | Unsupported schema/task/audience or malformed bounded input; show a safe validation message |
| `401` | Missing/expired verified session; reauthenticate |
| `403` | Current campaign/guild/role authorization is unavailable; refresh membership |
| `404` | No accessible proposal in the bound campaign; use the same response for unknown and foreign-owner IDs |
| `409` | Stale campaign/proposal/source context, invalid lifecycle transition or changed payload under an existing key; refresh and preserve the recorded outcome |
| `423` | Engine safety pause blocks a new generation/approval; keep saved records readable |

A provider failure is a persisted `failed` generation outcome with a safe code,
not permission to replay arbitrary paid calls or infer a narrative result.
Network/service failures with uncertain commit status require the original key
and owner-authorized refresh.

## Integration dependencies and acceptance

The Activity task must supply its repository/branch/commit, frontend/Embedded App
SDK state, backend framework/layout, existing API/client types, current verified
Discord session and guild-context flow, origins/proxy/hosting setup, live versus
demo state, active file ownership and its actual tests. Agree adapter ownership
before changing shared contracts. These missing details block direct Activity
connection, not the neutral contracts and synthetic engine workflow.

Before advertising this workflow as available, the Activity adapter needs one
verified-session → context → request → generate → private review → reopen
integration, with wrong-owner denial, current role revocation, stale-context
refresh, same-key retry and private-response checks. Engine focused synthetic
evidence belongs in the P2 acceptance report; it does not establish Activity
login, human narrative quality, complete P1 acceptance or full rules coverage.

No live campaign migration, bot restart, deployment, environment publication,
Discord transcript capture or real provider call accompanies this handoff.
The last verified live release remains v0.1.4 at
`fe47d7ef0b558a1106f5dc48b25c277aff5f875b`; its current process status was not
reverified by this development task. Preserve the frozen release and check its
private deployment record before any separately authorized operational change.

## Synthetic typed GM consumers (v3 proposal contract)

See [implementation and evidence](../../reports/P2_GM_OUTCOME_ADAPTERS.md). This
adds backend service calls, not HTTP routes or Activity components. Existing v1/v2
contracts remain available. The later Activity handoff should implement this flow:

1. From actual native work, select an existing choice, proposed battle context,
   pending Handler grant, open shared table stage or completed action. Server-side
   `GMOutcomeService.open(viewer, key, scene, source_kind, source_id, frame)` proves
   source and owner. Keep requires an explicit `TaskFrame` with goal demands and
   actual prerequisite references; it cannot silently infer a success threshold.
2. `packet` and `private` are administrative GM-only. Use the typed
   `OutcomePacket`/`OutcomeProposal` union in `ai/gm_outcomes.py`; `propose` accepts
   a manual proposal or injected provider. Do not put a full packet in a Handler
   prompt, shared Activity state or client log. There is no installed model.
3. Route `owner_review` to its actual original human owner. Present intended
   disclosures/effects as OOC review, with explicit confirmation. Do not treat
   platform administrator status as permission to confirm another owner's choice.
4. Call `confirm` with a durable command key. The server rechecks freshness inside
   the original native transaction and retains native follow-ups. On stale work,
   reopen the actual source; never resubmit an old proposal with a new revision.
5. Completed `narration` can be read through `contribution`, which combines intended
   approved text with that viewer's native projection. It is synthetic output;
   nothing here publishes to Discord or changes a committed outcome.

Owner-approved shared table outcomes use trusted
`owner_table_outcomes="gm_discretion"`. Show the real GM-owned
`battle_gm_table`/`wyvern_gm_outcome` controls, retain participant contributions,
and show the GM's final answer distinctly. A source of kind `table` can settle an
existing open shared stage after policy transition. Never auto-fill personal
choices or private answers. Existing policies default to `None` for frozen
compatibility; this is not a browser-controlled permission flag.

UI needs an actual-source work list, private GM proposal review, original-owner
confirmation, visible pending follow-ups, stale/reopen handling and per-viewer
outcome projection. Current Discord legacy forms are not the interface for these
new policy-selected table controls. Engine-first implementation intentionally
leaves that consolidated Activity work for later.

## Assisted player-test session coordinator and required Activity alterations

Current engine candidate: [player guide](../../docs/P2_PLAYER_TEST_GUIDE.md) and
[verification/findings](../../reports/P2_PLAYER_TEST_CANDIDATE.md). The earlier
v1/v2 status descriptions do not limit the new v3 native consumers. These are
Python contracts and a local synthetic development console; no route is installed.

`DirectorSessionService(context, conversation=None, outcomes=None)` reuses existing
services rather than maintaining another campaign state:

| Operation | Contract / UI responsibility |
|---|---|
| `submit(viewer, scene, AppendSceneInput)` | Returns saved `input` and discrete `conversation`. Persist the full original command/key for retry. A failure after input or GM success can resume with the same command. OOC input returns no conversation. |
| `work(viewer, scene, gm=False)` | Own native work/proposal metadata and own declarations. `gm=True` additionally requires actual configured GM authorization and returns source metadata for native GM adapters and all scene declarations. It never grants another participant's choices. |
| `bind_action(gm, key, scene, review_id, action_id)` | Exact Pilot declaration/Play/narration/author/incarnation proof; immutable metadata only. Show linked native state through completion. Do not bind another role/body by sharing a controller ID. Unsupported bindings retain manual review. |
| `contributions(viewer, scene)` | Approved intended text and that viewer's native projection, sorted by durable narration ordinal. Rechecks current consent, scene membership, safety and native access. Never treat the private GM log as the shared transcript. |

`work.outcome_sources` carries `source_kind`, `source_id`, `operation`, `owner_id`
and `frame_required`. Open only a real listed source with `GMOutcomeService.open`;
then follow private packet → proposal → owner review → confirmation. Proposed
battle contexts use the latest canonical record per ID. Closed contexts do not
reappear from their older proposed history.

`work.proposals.status` distinguishes `awaiting_confirmation`, `confirmed` and
`stale_reopen_source`. A native confirmation does not imply all subsequent owner
work is complete. `work.declarations` distinguishes real linked native state from
unlinked routing/clarification; `decision_current` tells whether an unlinked routing
note still matches its current fingerprint. A source edit becomes `source_stale`.
Triage remains with `DirectorPlayReviewService.review` and requires a fresh private
fingerprint. Unknown/disabled/unimplemented mechanics are not completed by triage.

Conversation rendering must honor the saved decision: show an ordinary GM reply
only for `gm_decision.action=RESPOND`. WAIT is diagnostic metadata. Handler reply
exists only after engine RESPOND; repeated unsolicited scope warnings with an
actual saved reply stay silent until the relevant role/scope changes. The new
`scope_already_addressed` reason is a WAIT reason. Direct requests remain eligible;
no fixed quota or general semantic pacing is claimed. The conversation provider
is still the bounded synthetic implementation; real-model free prose is not enabled.

Keep `owner_review.decision` now contains intended verdict/narration and excludes
all private assessment notes. Full assessment/reasoning belongs in GM-private
review only. OOC native Handler-owner confirmation is not fictional Handler speech.
The later Activity should distinguish these labels even when one human holds both.

Explicit retained knowledge uses the existing `DirectorContextService.record`:
ordinary observations keep their provenance; a confirmed `gm-narration:` source
can become an `approved_outcome` reference after actual completion/proposal/command,
text and original-audience checks. Add this classification to frontend enums.
The GM explicitly selects the actual known actors; no automatic omniscience is
granted. These references describe approved accounts, not new canon effects.

`DirectorContextService.archive(gm, key, scene, expected_context_revision,
reference_ids, reason)` retires selected active prompt references with an immutable
record. Require exact current IDs/revision; dependent references must be retained
or retired together. Keep history available to authorized GM review. Do not present
this control as deleting evidence, erasing character memory or a real-data privacy
redaction feature. Source corrections still require explicit reconciliation.

The consolidated frontend work is:

1. Real authenticated session → verified server principal and actual scene/role;
   current consent/safety/permissions on every read, write and reconnect. The
   console's `/as` fixture personas and trusted `synthetic=True` are never wire
   permissions or live-authentication substitutes.
2. Scene input/retry handling, separate visible GM/Handler interventions and quiet
   turns; stable source/reply IDs and native scene-lock feedback.
3. Role-specific work list, exact declaration/native-action binding, native choice
   forms and source-specific manual escalation. Preserve players' voluntary inputs.
4. Private GM framing/proposal panel, source evidence and separate actual-owner
   confirmation; stale/reopen flow, visible costs/follow-ups and GM-discretion
   shared outcomes. No browser-authored canonical effects.
5. Explicit knowledge assignment/retirement controls and ordered participant-safe
   approved readbacks. Invalidate cached protected data on scope/consent changes.
6. Feedback capture and human pacing/fairness evaluation, followed separately by
   real-provider usage/data handling, delivery/reconnect tests and live enablement.

The backend source work does not need the Activity repository to finish its
synthetic candidate. Connecting the real UI/authentication still needs that
repository's concrete server adapter and ownership. No real capture, provider
transport, Discord publication or deployment is supplied by this handoff.
## Connected-scene continuation (November 17 engine source)

See [four-part results and next-work review](../../reports/P2_CONNECTED_CAMPAIGN.md).
These additions require later Activity ports; they are Python service contracts,
not installed routes. The earlier packaged Activity ZIP does not contain them.

| Operation / field | Required Activity behavior |
|---|---|
| `DirectorSessionService.work(...).decision_routes` | Display `choice_id`, native `kind`, effective `owner_id`, `route`, `operation` and `confirmation`. `typed_outcome` means an adapter family exists; `outcome_sources` remains the validated source list for opening proposals. `native_owner` uses the original native form. Keep source-delegated authors; GM visibility grants no extra confirmation authority. |
| `decision_context(gm, scene, choice_id)` | Private, current GM review of a pending native choice, its real action/intent, references and canonical state. Never put this response in a Handler prompt, shared client state or participant transcript. It has no apply operation; consumed choices must be reopened from current work. |
| Knowledge topics `briefing`, `tactical`, `debrief` | Facilitator assignment marks actual role-known information eligible for a Handler update. Do not automatically label arbitrary chat or private GM facts as announcements. A reported claim stays a claim. Generation still requires persisted RESPOND; WAIT renders silence. Updates are considered on the next processed input, with direct questions and scope warnings taking priority. |
| Handler delivery state | Show actual saved replies and decision reasons, including `known_update` and `update_already_addressed`. A saved decision alone does not mean delivery. Successful replies suppress the same root update for the same Handler and roster across handoffs. Keep retries attached to the complete original command. |
| `SceneContinuityService(context).preview(gm, source_scene)` | Read the handoff source and revision even after its native scene closes. Pilots cannot join two active native scenes. Close the preceding scene through native controls, then join/configure/consent to the destination before selection. This GM-only preview is not a general closed-scene participant transcript API. |
| `.carry(gm, key, source_scene, target_scene, source_revision, target_revision, reference_ids)` | Explicitly select current references and all dependencies using preview's source revision and the destination context revision. Only the same roster is supported. Reopen both snapshots on stale context. The result maps old reference IDs to new ones and applies no native effects. Never enlarge known-by actors or treat handoff as new consent. |
| Reference origins | Optional `origin_scene` / `origin_reference` fields preserve root provenance. They appear together; default-null fields are omitted from ordinary legacy references. Existing classification and actor knowledge restrictions remain authoritative. Do not convert remembered claims into confirmed facts. |
| Closed-source withdrawal | A former participant may call existing `set_consent` with `consent=False` and the actual policy revision after closure. New grants still require an open scene. Carried context blocks if original consent is withdrawn; do not silently restore it or reuse cached generation. |
| `DirectorContextService.archive_review(gm, scene)` | Metadata-only IDs, dependency IDs and revision remain available for retiring blocked references. Pass that revision and an explicit dependency-closed selection to existing `archive`. Do not invent stale text or bypass freshness to repair the prompt. Current destination authorization/consent is still required. History is preserved; retirement is not fictional forgetting. |

Keep the native replacement flow in its real owners' forms: Pilot preferences,
Handler package quotation and Pilot acceptance, with required follow-ups visible.
The connected test proves replacement and a subsequent native Play; its Strain and
Off-Duty preparation remain open. No new mission acceptance, payment, full period
completion, autonomous provider, Discord publication or paid calls are implied.
