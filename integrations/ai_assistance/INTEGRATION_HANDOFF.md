# Activity integration — synthetic assistance v1

The owner's approved [Activity-first Director design](../../docs/AI_DIRECTOR_ARCHITECTURE.md)
and [next synthetic observation work order](../../docs/work_orders/P2_DIRECTOR_OBSERVATION.md)
extend the future product plan. They preserve this delivered summary v1 API.
Scene submissions, subscriptions/consent, batching, Director decisions, NPC/world
contributions and general Activity delivery remain planned, unregistered APIs.
Enabled NPC initiative/world proposals do not activate live mode. The observation
source is the authorized persisted Activity scene stream, not passive Discord
chat. Read the canonical design for UI and backend responsibilities before adding
those consumers; do not broaden `ReviewDraft` into a mechanical apply endpoint.

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
requested = service.request(verified_viewer, RequestAssistance(
    command_key="assist:request:unique-intent",
    expected_campaign_revision=context.context.campaign_revision,
    audience=context.context.audience,
    context_digest=context.context_digest,
))
draft = service.generate(verified_viewer, requested.proposal_id, GenerateDraft(
    command_key="assist:generate:unique-intent",
    expected_campaign_revision=requested.campaign_revision,
    expected_proposal_revision=requested.proposal_revision,
))
private_view = service.get(verified_viewer, draft.proposal_id)
# Present private_view.record.response; wait for the owner's explicit review.
approved = service.review(verified_viewer, draft.proposal_id, ReviewDraft(
    command_key="assist:approve:unique-intent",
    expected_campaign_revision=private_view.campaign_revision,
    expected_proposal_revision=private_view.record.revision,
    decision="approve",
))
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
