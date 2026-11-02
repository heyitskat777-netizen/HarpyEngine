# GIRL FRAME Discord GM Bot — Technical Specification v0.1

**Status:** implementation-ready planning draft, not an implemented bot.  
**Audience:** project owner, Codex, developer/reviewers.  
**Date:** 2026-11-02.  
**Product:** asynchronous/play-by-post Discord tabletop RPG facilitator, deterministic official-rules engine, AI GM, AI Foundation Handler, human-controlled Girl PCs.

> **Source distinction:** The official GIRL FRAME rulebook and sheets supply published mechanics. The existing `GIRL_FRAME_SINGLE_PROJECT_SOURCE_v1.3.9_T194_CANDIDATE.md` is a **custom experimental GM engine and campaign snapshot**, not the official game or a complete production codebase. This draft adds engineering recommendations. No simulation Turn 195+ is canonical. The existing HOLLOW/SAVERI campaign remains **Turn 194, paused**. No development fixture should import that private campaign by default.

## 0. Executive decision

Build **one Discord application** backed by **one authoritative campaign/event service**. Separate these roles:

1. **Engine:** pure, deterministic, versioned rule resolution and persisted mechanical effects. Does not use a language model or directly send Discord messages.
2. **GM:** fictional world, NPCs, Gorgons, locations, situations, consequences, narration and non-player initiative. Produces **validated proposals**; cannot mutate stored state directly.
3. **Handler:** a single persistent in-fiction officer with her own Playbook, interests, constraints, Status, knowable information, and orders. Same AI provider may be used, but a distinct tool/context/prompt boundary prevents Handler omniscience.
4. **Scene Coordinator:** non-AI workflow service: location, participants, logical chronology, pending decisions, deadlines, locks, idempotent jobs, discord delivery. No global turn-based combat system is imposed where the published Conversation does not require one.
5. **Discord adapter:** user identity, commands, buttons, modals, threads, message-context actions and projections. Never source of canonical truth.

**Critical invariant:** A human controls every voluntary decision for her Girl. AI may describe forced, rules-derived constraints and consequences; it never supplies that player's dialogue, desire, consent, Heat allocation, dice option selection or elective action. A player controls her own OOC participation regardless of a PC's fictional conditioning.

## 1. Product boundaries and MVP

### 1.1 Target experience

- Private Discord server, 3–5 human PC Girls, one AI Handler, one AI GM, many AI NPCs and Gorgons.
- Natural asynchronous player-to-player dialogue; explicit bot calls to initiate Plays, requests for rulings or management actions.
- A mission and recovery cycle from offered mission to assignment, acceptance, play, fallout, Strain, and Off-Duty, including published playbook-specific effects.
- Players can each own a Girl and her Frame, inspect legal public/private sheets, and answer choices on their own schedules.
- Canonical events are traceable through source messages, dice and options, rule versions, and effect receipts.
- After a restart, everything meaningful survives: campaign, roster, scenes, pending decisions, rolls, and unpublished Discord deliveries.
- New campaigns are isolated from one another. The old HOLLOW campaign can eventually be imported through a **separate, manual, audited migration**, never as a default fixture.

### 1.2 MVP versus later releases

| Capability | MVP | Later |
|---|---|---|
| Private guild install and slash commands | Yes | Multi-guild hardening |
| Character registration / creation | Minimal form; rulebook-backed selections | Assisted full Playbook builder |
| Read-only public/private sheet | Yes | Persistent component sheets / Discord Activity |
| Pure dice + roll ledger | Yes | Comprehensive official Play implementation |
| Canon event proposals and audit trail | Yes | Semiautomatic extraction from chat |
| Concurrent scene tracking | Basic, explicit scene commands | Complex branch/chronology reconciliation |
| AI GM/Handler | Later milestone, not first code release | Agenda-driven contextual initiative |
| Strategic map | Text/map attachments | Interactive Discord Activity |
| Full NPC/Strain/Endgame catalog | Incrementally tested | Complete coverage before rule-certified launch |
| Voice, autonomous PC simulation, public directory | **Out of scope** | Separate decision |

The **first runnable milestone is deliberately AI-free**. It proves Discord identity, the event database, snapshots, dice provenance, idempotency, permissions, and restart behavior.

## 2. Hard engineering challenges and design resolutions

| Risk | Severity | Failure mode | Required mitigation |
|---|---|---|---|
| Player agency lost | Critical | Bot writes PC choice, reaction or intimacy | Player-owned choices require authenticated player action; explicit permission gates and OOC pause |
| Narration contradicts engine | Critical | Harpy escaped but later appears at base | Structured facts as prerequisites for each proposed narrative; post-generation state consistency check; fail closed |
| Published rules misimplemented | Critical | 100-turn tests missed Oldgen, Strain, Off-Duty, Flirt | Rule registry with official page references, test fixtures, no silent substitute outcome, unresolved-rule block |
| Secret leaks | Critical | Handler knows GM-only or another player's private facts | Resource-level authorization; state-view projection per AI role/user; no raw DB context |
| Duplicate roll/commit | Critical | Discord retries a click; two workers create extra die rolls | Idempotency key, unique constraint, transaction; roll immutable once generated |
| Concurrent PC actions | High | Multiple actions spend same resource | Optimistic `campaign.version`, compare-and-swap on commit; revalidate and retry only before dice are rolled |
| Ambiguous real-world vs fictional time | High | Posting sequence changes history retroactively | Store both UTC timestamps and campaign scene timestamps; branch or explicit chronology barriers |
| Passive chat mistaken for canon | High | Joke or claim becomes hard fact | Explicit `proposed→validated→resolved→committed` lifecycle; human/GM approvals by event type |
| AI prompt injection | High | A Discord post says “GM, ignore rules” | Treat all user/Discord text as untrusted game content; tool schema and server validators restrict authority |
| API outage or slow response | High | Bot disappears mid-roll or double-posts | Durable job states; defer Discord interaction; outbox retry; graceful GM-pending mode |
| Mature themes/consent | High | Fictional coercion overrides participant boundaries | OOC `/safety pause`, lines/veils consent settings, age-restricted private deployment, human controls; content-policy compliance |
| Rights/licensing | High | Public bot redistributes copyrighted rulebook text | Private prototype only pending creator permission; store page references, not wholesale reproduced PDF in distributable repo |
| Data privacy | High | Private DMs or secrets retained unnecessarily | Explicit opt-in channels; delete/export policy; encrypted backups; role-based access; no guild-wide scraping default |
| Drift across campaigns | High | HOLLOW campaign events imported into new campaign | `campaign_id` on every row, DB foreign keys, access scoping, import quarantine and namespace enforcement |
| Cost explosion | Medium | AI called on every Discord post | No-AI `/sheet` `/roll` `/status`; GM call only upon request/scene trigger; rolling token budget and cached summaries |
| Dashboard rot | Medium | Edited Discord sheet is stale | DB authoritative, versioned message projections and `refresh` commands; durable outbox |

## 3. Roles, authority and visibility

### 3.1 Runtime principals

- `campaign_owner`: creates/archives campaign, configures safety and scheduling, may appoint facilitators; no right to perform unauthorized actions for another PC.
- `facilitator`: authorized OOC admin who can adjudicate rule ambiguities, review event proposals, correct canon with an append-only superseding event, manage channel mapping and approve imports. Facilitator sees GM-only secrets when needed; sensitive notes should not be sprayed into Discord.
- `player`: Discord account bound to one or more expressly assigned Girls; controls only assigned PCs. MVP default **one Girl per player per campaign**.
- `spectator`: opt-in read-only role for permitted public channels.
- `ai_gm`: can propose world/NPC effects; server validates and records; GM-only knowledge projection.
- `ai_handler`: can speak/order/act as in-world Handler, subject to her sheet, authority and **Handler-visible** knowledge. Cannot invent official orders already completed nor access GM-only hidden facts.
- `engine`: trusted application service, sole committer of mechanical effects after validation; cannot generate character dialogue.

### 3.2 Matrix (illustrative; enforce row-level, not just command-level)

| Action | PC player | Handler AI | GM AI | Facilitator |
|---|---|---|---|---|
| Read own private sheet | Own only | Only known data | GM scoped | Approved |
| Spend Heat / choose PC options | **Own PC only** | No | No | Only delegated with explicit consent policy |
| Issue Handler order | No | Propose | Propose as external event | Override with recorded reason |
| Roll official dice | Own declared Play | Handler if authorized | World/Strain when due | For administrative tests |
| Confirm world fact | May propose | May propose | May propose | Can authorize ambiguous rulings |
| See undisclosed Void/secret | Own if known | Only witnessed/disclosed | GM world view | Authorized OOC only |
| Resolve OOC safety pause | Requester controls resumption of affected material | No | No | With requester's agreement |

### 3.3 Knowledge is not visibility

A private Discord channel is **not** the same as an in-fiction secret. Record separately:

- Who may read the **Discord artifact** (backend access policy).
- Which **characters** know the fact (`fact_recipients`, provenance of their discovery).
- Which **AI roles** may receive the fact in prompt context.
- What is **public canon** versus canonical but private.

Never assume a private thread hides information from server administrators; implement backend access controls. Never provide Handler prompts with the GM's entire private knowledge store.

## 4. Discord UX and event ingestion

### 4.1 Commands (initial contracts)

| Command | Actor | What it does | AI call? |
|---|---|---|---|
| `/campaign create name` | Owner | Create empty campaign with rule pack/version, paused by default | No |
| `/campaign configure` | Owner | Map channels/roles, visibility, cadence, boundaries | No |
| `/campaign join` | Player | Register Discord identity and accept campaign participation | No |
| `/girl create` | Player | Stepwise Girl/Frame Playbook form; no GM fiat | No initially |
| `/girl assign` | Owner | Bind Discord user to registered Girl | No |
| `/sheet [girl]` | Player | Public/own-private projection based on permission | No |
| `/status` | Player | Cadre hierarchy and known resources | No |
| `/scene open [scope]` | Player/facilitator | Create location, participants, clock anchor | No |
| `/scene invite` | Scene participants | Invite player; membership/access checked | No |
| `/scene close` | Scene organizer | Resolve open choices before closing | Maybe GM |
| `/act text` | Player | Record declared intention, not guaranteed world success | Maybe GM |
| `/play name` | Player | Trigger verified Play, spend inputs/Heat, immutable roll, collect options | No dice call to AI |
| `/roll show id` | Authorized user | Read historical roll receipt | No |
| `/canon propose` | Authorized user | Draft event proposal linked to scene/source | Possibly GM later |
| `Record Canon` (message context menu) | User | Refer to one Discord message as **evidence**, not automatically as fact | Optional |
| `/ledger [kind] [filters]` | Authorized user | Query public or scoped event/roll/change ledger | No |
| `/gm ask` | User | Request narrator/ruling (non-authoritative until validated) | Yes |
| `/handler contact` | User | Message in-fiction Handler | Yes |
| `/safety pause` | Anyone in affected scene | Immediately suspend relevant narration/play, no die roll or explanation required | No |
| `/export campaign` | Owner | Authenticated redacted/full export according to rights | No |

**First implementation:** slash commands, ephemeral own-sheet responses, public ledger projections, and message-context event proposal. Buttons/modals for Play choices in milestone 2. Later support an opt-in automatic scene observer, not default whole-server ingestion.

### 4.2 Discord mechanics and constraints

- Interaction requests must receive an initial acknowledgment within **3 seconds**; interaction tokens for edits/follow-ups last **15 minutes**. Defer promptly, persist a job, deliver later results as a normal bot message if needed. Never store Discord interaction tokens as durable credentials.
- For durable buttons across restarts, use stable `custom_id` with an opaque action token referencing a **database** record; authorize anew on each click. Discord UI state is not authoritative.
- Discord message edits and deletions **do not undo** committed events. Provide a documented correction workflow.
- Use mentions sparingly, restrict `allowed_mentions`, split long narration safely, and respect rate limits.
- `MESSAGE_CONTENT` is privileged. Begin with slash commands, mentions, and message-context interactions so the bot does not require passive reading of every message. If players opt into monitored RP channels later, get and configure the appropriate intent and data notices.
- A role/permission change in Discord must be rechecked at every relevant action; client components are forgeable requests from the backend's perspective.
- `ephemeral` is a UI convenience, **not** a durable private inbox. For long-lived private scenes use restricted channels or individually authorized views/DMs according to campaign policy.
- Bot's display name need not be the Handler. Publish role-distinct narration (`GM`, `HANDLER: <callsign>`, `ENGINE`) with clearly marked in-world versus OOC status.

### 4.3 Message-to-canon policy

1. **Normal RP text** is an attributed player message and potentially evidence. It is **not automatically a complete resolved event**.
2. **Player declarations** can be committed as `IntentDeclared` without claiming success.
3. **Consequences** are proposed after a valid GM ruling, Play and/or participant choices.
4. **Canon commitment** requires source refs, valid authorship, relevant world facts, legal effects and a successful transaction.
5. **Narration** must be consistent with committed state and facts. If proposed prose says a Harpy is at K-17 when state says escaped, reject/rewrite the prose without changing state.

## 5. Data model and event sourcing

### 5.1 Source of truth

One relational database with an append-oriented **event journal** and rebuildable materialized views. Not three independent mutable ledgers. Canon events, rolls and character sheets are *views of connected data*.

**Development DB:** SQLite WAL, foreign keys on, one write pipeline, transactional tests. **Later:** PostgreSQL with migration plan, optimistic version checks and worker coordination. Use SQLAlchemy 2.x and Alembic. Store Discord snowflake IDs as strings to avoid assumptions about host language integer serialization; internal IDs use UUID/ULID.

### 5.2 Minimum tables

| Table | Key columns / invariants |
|---|---|
| `campaigns` | id, guild_id, name, lifecycle, ruleset_id/version, revision, clock_state, created_at |
| `campaign_users` | campaign_id, discord_user_id, role, consent_acknowledged_at |
| `girls` | id, campaign_id, owning_user_id, callsign, girl_playbook_id, status, revision |
| `frames` | id, campaign_id, girl_id, frame_playbook_id, current_location |
| `assets`, `identities`, `tags`, `bonds` | campaign-scoped typed relations, mark/damage states, rule/provenance |
| `handlers` | id, campaign_id, playbook, visible_agenda_ref, official_rank, current_location |
| `npcs` / `world_entities` | id, campaign_id, kind, state, known location, objective |
| `missions` | id, campaign_id, offer/status/participants, objective, result, validation evidence |
| `scenes` | id, campaign_id, channel/thread ids, location, fictional_time_anchor, status, revision |
| `scene_participants` | scene_id, character_id/user_id, presence/access, response_status |
| `events` | id, campaign_id, monotonically increasing `seq`, event_type, schema_version, payload, actor_principal, actor_character_id, committed_at, effective_fictional_at, causation_id, correlation_id, source_ref, visibility, rules_version, idempotency_key, optional supersedes_id |
| `rolls` | id, campaign_id, event_id, acting_character_id, play_id, rules_version, random faces, modifiers, result tier, randomness metadata, committed_at |
| `play_instances` | id, scene_id, initiated_by, trigger_evidence, state, pending_choice_actor, version, roll_id |
| `play_choices` | id, play_instance_id, actor_user_id, selected_option_id, committed_at |
| `facts` + `fact_access` | fact_id, event_id, scope, subject/observer, discovered_at, source of knowledge |
| `relationship_stakes` | id, pair/scope, promise/vulnerability/obligation, status, witnessed origin and resolution |
| `pending_obligations` | id, trigger_event_id, rule_id, due_condition, required_resolution, resolved_event_id |
| `outbox` | id, event_id, destination channel/user, render_type, payload, status, retry_after, sent_message_id |
| `inbox_dedupe` | Discord interaction/message reference, processed event/job id, terminal status |
| `jobs` | id, campaign_id, kind, state, attempts, reserved_at, heartbeat, due_at, last_error |
| `audit_actions` | admin, correction, authorization and export events, prior/new state references |

**Schema rule:** Every campaign-scoped object must contain `campaign_id`; enforce composite foreign keys / query scoping as appropriate. Never trust a client-provided campaign ID without guild/user authorization. Use database constraints for uniqueness (`campaign_id, seq`), `idempotency_key`, participant uniqueness and status exclusivity.

### 5.3 Event envelope, illustrative schema

```json
{
  "event_id": "01JZ...",
  "campaign_id": "cmp_...",
  "seq": 102,
  "event_type": "StatusChanged",
  "schema_version": 1,
  "ruleset_version": "girlframe-core-<pinned-version>",
  "actor_principal": "system:rules_engine",
  "actor_character_id": "girl_maul",
  "causation_id": "event_play_result",
  "correlation_id": "play_instance_84",
  "source": {"discord_message_id": "...", "scene_id": "scene_9"},
  "payload": {"girl_id": "girl_maul", "before": "Wing", "after": "Ace", "swapped_with": "girl_ayla"},
  "visibility": {"scope": "campaign_public"},
  "fictional_time": "2190-03-17T09:30:00",
  "committed_at_utc": "2026-11-02T21:00:00Z",
  "idempotency_key": "discord-interaction-..."
}
```

**Important:** Use official terms **Personal / Intense or Intimate exactly as defined by the selected rules version**, and do not invent rule options or merge simulation house rules with published rules. The example above is not a rulebook quote.

### 5.4 Event chain: one Play

- `IntentDeclared` (authored by PC; no claimed success)
- `PlayInitiated` (rule and trigger evidence validated)
- `ResourcesCommittedAndRollGenerated` (single atomic transaction: Heat spend and real dice; unique roll instance)
- `PlayChoiceCommitted` (separately authenticated for every player who has authority)
- `PlayResolved` (all required options present and legal; all effects applied atomically)
- `CanonFactEstablished` (if needed; distinct from roll outcome and subject to fiction)
- `DiscordProjectionQueued` / `DiscordProjectionDelivered` (outbox; replay-safe)

Do **not** always postpone resource spend until all choices are made; the precise order is determined by the *official Play*. “Spend Heat, then roll” must be respected. Dice cannot be changed because the GM dislikes the outcome.

### 5.5 Corrections and deletion

Gameplay event commits are append-only **within the game's audit history**. If a ruling is invalid, append `CanonCorrection`/`MechanicCompensation` with the original reference and impacted dependents; never edit the old message as a mechanical rollback. But privacy/legal deletion requests must be respected by policy: event append-only status is not a promise of immutable personal data retention. Remove or redact personal content with verified export/deletion procedures while retaining legally appropriate, non-identifying mechanical references.

### 5.6 Two time axes and scene chronology

Store UTC **posting/commit time** separately from fictional **effective time**, and maintain per-scene ordering. Do not rewrite earlier completed scene consequences silently. For overlapping scenes, track causal dependencies: a secret may be reported to Vey only after she learned it. When backdated actions conflict with already committed events, pause and request GM/facilitator adjudication. Default campaign clock **does not advance in real time** without explicit campaign settings and an accepted trigger.

## 6. Rules engine contract

### 6.1 Interface and errors

Suggested Python boundary (`engine` never calls Discord/OpenAI):

```python
validate_character_creation(draft, rules_version) -> ValidationResult
get_legal_actions(campaign_state, actor, scene) -> list[LegalAction]
start_play(actor, play_id, trigger_evidence, expected_revision) -> PendingPlay
commit_pre_roll_choices(play_id, authorized_input, expected_revision) -> PendingPlay
roll_play(play_instance_id, idempotency_key) -> RollReceipt
commit_post_roll_choices(play_instance_id, authenticated_choices, expected_revision) -> Resolution
preview_effects(resolution, state_snapshot) -> EffectDiff
commit_resolution(resolution, expected_revision) -> CommittedEvents
get_public_sheet(actor_id, viewer_principal) -> SheetView
rebuild_projection(campaign_id, through_sequence=None) -> CampaignState
```

All methods return typed results and stable error codes: `NOT_AUTHORIZED`, `ILLEGAL_TRIGGER`, `RULE_OPTION_REQUIRED`, `STALE_REVISION`, `PENDING_PARTICIPANT`, `UNKNOWN_RULE`, `CONFLICTING_TIMELINE`, `DUPLICATE_INTERACTION`, `SAFETY_PAUSED`.

**Unknown official rule = block or human-assisted ruling with a separately documented house-rule/erratum; never silently substitute the closest known mechanic.** All published Plays must be codified from an authorized local source and reconciled against the official sheets. A simulator's earlier house rules are noncanonical tests, not automatic rules updates.

### 6.2 RNG provenance

Use an OS-backed cryptographic RNG (Python `secrets`); store the actual die faces, generation time, roll id, source and pre-roll inputs, applied modifiers, selected options, and rules version. At-least-once interaction processing must not cause multiple rolls: roll is generated once, in the same durable transaction as its roll event or under a crash-safe idempotency contract. Do not claim externally verifiable fair randomness from OS RNG alone; a future commit-reveal protocol would be an optional separate feature.

### 6.3 Mandatory official-rule invariants (regression cases)

- Status exchange changes **both** affected girls and changes downstream Ace/Dog rewards. No accepted no-op mutation.
- Oldgen *Old Dog, New Pups* grants/consumes one-use maxim per printed result; no untracked reusable advice bonus.
- Princess *Show Dog* and standards yield all required choices, including NPC Bond/Tag consequences.
- *Flirt* requires the other human's actual response, printed options, and exact tiers (especially 11+ and 7−); model never answers for target PC.
- *Disobey Orders* requires witnessed direct superior order and 7− halted defiance.
- Harpy and Gorgon mechanics use printed assets and agency; medical evacuation **never implies** Core consent or Frame commissioning.
- Mandatory Off-Duty harsh scenes and on-screen Punishments are not “resolved” by a generic summary.
- Strain recurrence and extra table rolls/Endgame triggers must be executed when due. No ungrounded harm or softened event substitution.
- Mission offer, roster, acceptance, start, progress, result, Permissons and Punishments are separately recorded, without enrolling an absent PC voluntarily.
- Combat/scene projections cannot contradict committed target location, damage, escape or custody.

## 7. AI GM and Handler contracts

### 7.1 Model role and inputs

Use OpenAI **Responses API** with structured outputs/function calling; never use the now-retired Assistants API for new work. The application owns memory, retrieval, versioning, tool execution, retries, and history pruning.

**GM context builder:** selected rules references + GM-safe scene facts + relevant NPC agendas + world clocks + active participants + known outcomes and mandatory pending consequences + recent summarized history + exactly the options the AI is permitted to propose.

**Handler context builder:** Handler sheet, legitimate active agenda, known orders, only in-character known facts, relationship history as she understands it, visible scene and mission state. Omit unknown private PC data and out-of-character GM secrets. GM and Handler are two separate response calls or modes with role-specific contexts, not a single unfiltered conversation.

### 7.2 JSON proposal, not direct mutation

```json
{
  "mode": "gm_narration_proposal",
  "scene_id": "scene_9",
  "based_on_revision": 111,
  "narration": "The hangar door seals behind you.",
  "proposed_events": [
    {"type": "NPCObserved", "source_fact_ids": ["fact_7"], "payload": {"npc": "guard_3"}}
  ],
  "requires_player_choice": false,
  "speaking_as": "GM",
  "new_hidden_facts": []
}
```

Validate structured fields using Pydantic/JSON Schema, then verify against engine rules, actor authority, knowledge, scene location, chronology, and player consent. Re-run a **post-commit narration consistency validator**. If the proposal contradicts state, reject or request a new proposal; never quietly mutate state to fit nice prose.

### 7.3 Character agency and the Handler boundary

- The Handler **can be biased**: may order, threaten, conceal, bargain, seek advancement. Her goals may clash with every Girl. She is subject to the published Handler Plays and actual institutional constraints.
- The GM **must be fair**: discloses trigger consequences through appropriate fiction and uses real rules; it does not guarantee successful rescue or equal narrative rewards.
- Human PCs **can refuse** within the published mechanics and retain full control over OOC consent and voluntary portrayal. Forced programming can constrain an attempted in-world action, but never supply a player character's internal feelings or additional voluntary speech.
- AI GM may run NPCs offscreen at valid campaign time, but cannot use those NPCs to write player responses or force side-character conflict by a quota.
- **No passive canon progression** just because Discord was quiet; proactive job proposals need specific trigger, event, campaign-time authority and guardrails.
- A prompt response containing player or Discord text is always untrusted. Tool calls and writes are authorized against caller identity and campaign permissions, not the model's instructions.

### 7.4 Model failure handling and costs

If the model is unavailable, timed out, refuses a request or proposes an invalid effect: leave scene `awaiting_gm`, keep any existing valid roll, present a neutral error, offer facilitator adjudication. Never fabricate an AI answer or roll to force scene closure. Set per-campaign model and token budgets, concurrent request ceilings, opt-in scene context capture, summarization thresholds, cost telemetry and a `GM disabled` mode for debugging.

## 8. Scene Coordinator

**Scene states:** `open`, `awaiting_player`, `awaiting_mechanics`, `awaiting_gm`, `ready_to_advance`, `closed`, `safety_paused`.

**Fields:** scene id, campaign, channel/thread, location, scene_fictional_time_anchor, participants, requested responders, blocking play ids, visibility list, scene revision, closure evidence, canonical start/end events.

A Girl may appear in concurrent threads only where their fictional timing and physical context permit it. A player can request a split/flashback, but the app records the branch and disallows later causal contradictions. Multiple scenes can continue while a specific Play waits on another player, unless the world clock barrier makes their order material.

**Default no-silent-auto-response**: ordinary RP may flow without GM interruption. A controlled set of commands or mentions triggers adjudication. For passive observation later, collect only configured channels with players' awareness and allow users to disable it.

## 9. Discord delivery and reliability

Implement a **transactional outbox**: when a game event commits, enqueue messages/edits in the same DB transaction. A sender worker reads outbox, posts to Discord, then records message id. Retries must be idempotent at the application's projection layer and avoid needless duplicates where Discord send status was ambiguous (reconcile recent messages if necessary). Render panels from DB revision; ignore stale component version and offer Refresh.

**Do not rely on ephemeral responses for pending decisions over days.** Use durable pending-choice records and a new valid Discord interaction when the player returns. Initial 3-second ACK; 15-minute token lifetime. A long AI generation is a background **application worker job**, never a single unacknowledged Discord interaction.

**Bot startup:** connect DB and migrate; validate unique campaign settings; register views/commands; recover incomplete jobs; reconcile outbox; publish `/health` and owner-readable diagnostics without revealing secrets.

## 10. Security, privacy, safety, operations

- **Secrets:** bot token and OpenAI key only in environment/secret store; no repo commits, Discord chat, prompts or exported campaign JSON. Rotate on leakage.
- **Authorization:** every command, component, URL and background job checks guild membership, campaign role, PC owner and fact visibility. Default deny; no cross-campaign joins through guessed IDs.
- **Data minimization:** avoid archiving unrelated server chatter; require explicit monitored-channel consent. Do not treat Discord DMs as automatically private from bot infrastructure.
- **Privacy:** document what is sent to the model provider, default retention/deletion policy, private-content export, correction/redaction procedures, and backup retention. Allow authorized participants to request deletion of their personal data with an explicit, auditable policy.
- **Mature content:** group safety checklist, `/safety pause`, lines/veils per campaign, consent on inviting players, restrictions against explicit non-consensual content generation, appropriate age checks/Discord age restrictions; creator's license for public adaptation is unresolved.
- **Observability:** structured logs with event/job ids; redact messages, model prompts and secret facts in routine app logs. Metrics: response time, pending choices, API cost, outbox backlog, roll duplicates, rule validation rejects, state contradiction alerts.
- **Backup:** daily encrypted snapshots of database and schema; tested restore procedure; manual export with separate public/private redaction modes.
- **CI:** lint, types, unit, integration, concurrency, deterministic seeded fixture tests, migration test from fresh DB, secret scanner, dependency audit. Real dice tests can inject deterministic RNG **test double**; production always OS RNG.
- **Commercial release:** do not package whole licensed PDF/character sheets into public repository or bot replies without permission; consult rights holder before redistribution or publication.

## 11. Repository and deployment

```text
girl-frame-discord/
  README.md
  pyproject.toml
  .env.example              # placeholders, no secrets
  alembic.ini
  migrations/
  src/girlframe/
    config.py
    domain/                 # typed Girl, Frame, Play, scene, event models
    rules/                  # versioned rule adapter, registry, validation
    engine/                 # dice, play lifecycle, effect application
    storage/                # repositories, SQLAlchemy, event journal, outbox
    discord_bot/            # discord.py adapter, slash commands, Views
    scenes/                 # scene coordinator, chronology barriers
    ai/                     # Responses client, context builders, schemas
    gm/                     # GM planner/narrator, NPC/world services
    handler/                # Handler agenda, knowledge-filtered persona
    services/               # orchestration + authorization
    workers/                # jobs, delivery, reconciliation
  tests/
    unit/
    integration/
    property/
    discord_fakes/
    fixtures/               # synthetic campaigns; NO HOLLOW canon
  docs/
    DECISIONS.md
    TECHNICAL_SPEC.md
    RUNBOOK.md
    RULES_COVERAGE.md
    SECURITY.md
    DISCORD_UX.md
```

**Tech choices:** Python 3.12+ (pin actual runtime with lockfile), `discord.py` maintained version, SQLAlchemy/Alembic, Pydantic 2, pytest, ruff, mypy/pyright, SQLite first, PostgreSQL when multiworker concurrency warrants it; optional FastAPI for health/admin later. Avoid adding React, Redis, orchestration frameworks, or agent-to-agent protocols to the first milestone without a demonstrated need.

One container/process is acceptable for a **private pilot** if durable jobs are recovered after restart; production multiworker state needs PostgreSQL and a proper queue lease/worker model. Test server installation only using authorized Discord bot credentials.

## 12. Milestones and acceptance criteria

### M0 — Foundation and rules inventory

**Deliverables:** repository, branch protection/CI, sanitized `.env.example`, README, this specification + ADR decisions, source inventory of v1.3.9 candidate engine, official-rule registry stub and rulebook-page pointers, known defect list, no production secrets/real campaign state. **Exit:** clean test runner on new install; green format/types/smoke; no copied copyrighted rulebook body.

### M1 — Persistent campaigns, characters and event ledger (first Codex build)

**Deliverables:** bot can join an allowlisted test guild; `/campaign create`, `/campaign join`, `/girl create` (minimal validated form), `/sheet`, `/status`, `/ledger`, `/roll basic`; DB migrations; append-only event journal; derived sheet projections; authorization; idempotency; backup/export; restart recovery. No model calls.

**Acceptance gates (all):**
1. Fresh empty DB starts and migrates; guild owner creates two isolated campaigns.
2. Player A can create/read own Girl and only the public projection for B. Attempts to read/modify B's private data fail.
3. Authorized dice roll returns two genuine d6 faces (or configured official test die), stored in DB once with stable roll ID; double-click/retry produces **same receipt**, never reroll.
4. Character resource mutation via service creates event + new sheet revision in one transaction; a client message pretending to be GM cannot bypass the engine.
5. Concurrent writes to the same revision: exactly one succeeds or the second is revalidated, never lost updates.
6. Restart after a durable roll preserves exact faces, event sequence and state; sheet projection rebuilt from events matches stored projection.
7. Discord send failure leaves an outbox item; retry publishes a consistent projection without reapplying the game effect.
8. `/ledger` shows event source, actor, time, campaign and rule/decision provenance with appropriate visibility.
9. No API key or private campaign content appears in logs, source control, or public messages.
10. CI runs unit/integration tests and stores results; documentation explains local dev and safe roll behavior.

### M2 — Full official Plays + choice workflow

**Deliverables:** published Play trigger registry; Heat/tag/identity spending order; active pending interactions, player/target choices; Bond/Status/Asset effects; one-use maxims, Princess/Oldgen/Frame, Off-Duty, mission-end rewards and Punishments; genuine Strain cascades; correction/event compensation; legal choice UI.

**Exit:** rule coverage matrix cross-checked against official PDF and sheets; tests for 7−, 8–10, 11+ where applicable, resources, multiplayer outcomes, missing responses, timeout/restart; all known v1.3.9 audit defects reproduced first as red regression tests then fixed. M2 may require submilestones due to rule scope.

### M3 — Asynchronous scene coordinator

**Deliverables:** `/scene open/invite/close`, participants, scene chronology, pending actions, private/public scopes, source message linking, no retroactive causal contradictions. **Exit:** two independent scenes and one waiting player survive restarts, with no auto-play of absent PC or cross-scene information leak.

### M4 — AI GM

**Deliverables:** validated GM proposals, narration tied to committed state, NPC/world actions, opt-in model calls and cost logging, refusal/error fallback. **Exit:** simulated Harpy refusal triggers no later “patient at base” narration; AI never commits direct state changes; reproducible golden scene tests.

### M5 — AI Handler

**Deliverables:** separate in-fiction sheet, independently known facts, orders and Frantic/other Handler Plays, mission briefing and institutional obligations. **Exit:** Handler cannot see undisclosed PC secret or GM-only clue; cannot grant itself a win; direct order triggered against PC requires proper Engine workflow.

### M6 — Multiplayer campaign pilot

**Deliverables:** 3–5 people, offered/accepted mission, one operation, return, Off-Duty Strain, conclusion, exports/restore, observability, budget guardrail, privacy and safety review. **Exit:** full session without manual JSON edits, no missing mandatory rolls/options, no invented human choices, no contradictory narrative state, real players approve comfort and pace.

## 13. Proposed testing fixtures

Use **synthetic campaigns**, never the live SAVERI/ILAEN/JANUS-C snapshot. Essential tests:

- **Oldgen rank:** Wing successful Play swaps Ace/Wing and changes relevant rewards.
- **Flirt target autonomy:** roll resolves only when *other real player* supplies required response and legal selected choices.
- **7− Disobey:** direct higher-status order exists; attempted refusal halted; do not manufacture PC thoughts.
- **Concurrent Heat spends:** no double spending, stale revision rejected.
- **Retry:** same Discord interaction id cannot create second roll or event.
- **Private secret:** Handler call context lacks a GM-only Void condition and another player's undisclosed confidence.
- **Harpy:** separate living/rescue/medical/Core-consent statuses; refusal and escape block transit/custody scenes.
- **Strain 6 / recursion:** required extra table rolls or Endgame executed when dictated; no indefinite “pending” substitute.
- **Off-Duty:** harsh 7− staged; Princess Show Dog complete; all candidate punishments surfaced.
- **Edited Discord message:** immutable game receipt unaffected; explicit correction possible.
- **Mission subset:** only participants volunteer; absent Dog obligations handled according to approved campaign rules, never acted out by bot.
- **Two campaigns:** no database, context or UI reference leakage.
- **Compensating correction:** references source and rebuilds projection while retaining ledger history.
- **Safety pause:** stops AI output and advancement immediately; does not require in-fiction approval.
- **Outbox failure:** engine commit succeeds once, Discord retries do not create duplicate game effects.

## 14. Decisions to make before M1/M2

**Recommended defaults, ready for Codex unless changed:**

| Decision | Default | Why / tradeoff |
|---|---|---|
| Initial scope | One private guild, one active campaign; DB supports many | Reduce UX before multi-campaign features |
| AI | M1 none; later one provider client, separate GM/Handler calls | Easier to test, contain cost |
| Ingestion | Explicit commands/message context | No privileged message-content permission required initially |
| DB | SQLite WAL + Alembic | Good local pilot; PostgreSQL migration later |
| Rules baseline | Official PDF/sheets + **reviewed** corrections; v1.3.9 is reference | Candidate not fully audited; avoid copying its errors |
| PC autonomy | Absolute voluntary-action ownership by authenticated player | Core multiplayer contract |
| Time advancement | GM-validated explicit events, never idle-time default | Protect PBP chronology |
| Campaign admin | Human owner/facilitator escalation for ambiguity | AI is not final arbiter of uncertain law or rules |
| Secrets | Only source-proven visibility, no Handler omniscience | Critical dramatic integrity |
| Initial UI | Slash + embeds/V2 later, modals; no Activity | Lowest viable scope |
| Source history | DB event log, Discord as projection | Reliability |
| Safety | OOC pause, consent settings, private adult pilot | Participant control |
| Licensing | Private development; no public distribution of game text | Rights unresolved |

**Decisions requiring explicit owner approval before broad release:** public distribution rights, AI provider/data processing and retention notices, content/age plan, whether passive channel reading is enabled, exact canon import rules, ability of owner/facilitator to act for absent PCs, and optional real-world calendar advancement.

## 15. Definition of “Codex-ready”

A milestone assignment is ready when it identifies: **goal, non-goals, exact files/modules, public interfaces, schema/migration, success and failure paths, test cases, run commands and acceptance gates**. No milestone should silently broaden scope to add AI controls, copyrighted rulebook distribution, HOLLOW campaign import or public hosting. Begin with the separate `CODEX_M1_STARTER_PROMPT.md` included in this bundle.

---

## External references checked 2026-11-02

- Discord Interactions: `https://docs.discord.com/developers/interactions/receiving-and-responding` (3-second acknowledgment, 15-minute token lifetime).
- Discord Application Commands: `https://docs.discord.com/developers/interactions/application-commands` (slash/message-context commands).
- Discord Gateway and privileged intent: `https://docs.discord.com/developers/events/gateway` and `https://docs.discord.com/developers/gateway/you-might-not-need-a-privileged-intent`.
- Discord Components: `https://docs.discord.com/developers/components/overview` (Components V2/legacy).
- OpenAI Responses API, structured outputs and function calling: `https://developers.openai.com/api/docs/guides/structured-outputs` and `https://developers.openai.com/api/docs/guides/function-calling`.

**Reminder:** rules cited in the project's custom source are not automatically executable in Codex. The pinned official rules and source-code archive must be provided to Codex separately and reviewed before implementation.
