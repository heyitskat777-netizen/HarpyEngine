# Activity-first interface — staged integration contract

Owner direction: make the Discord Activity the primary interface and isolate the
bot's Discord-specific responsibilities. Preserve the existing architecture,
campaign authority and live release while integrating in bounded stages.

The owner supplied an Activity thread link. This session has no tool
that reads another Codex thread. Its repository, framework, authentication,
backend and hosting remain unverified; the thread link is not source access.
The other task must provide its current architecture/API handoff before a
matching live connection can be implemented. The delivered v0.1.4 JSON kit remains
the tested compatibility baseline, not an existing Activity API.

## Target ownership

| Component | Owns | Boundary |
|---|---|---|
| Discord Activity | Creation editor, sheet views, requests inbox, Play selection and owned decision forms | Displays authorized server projections; no browser SQL, Bot Token, roll generation or canonical writes |
| Authenticated application backend | Activity sessions, verified user/guild/role context, typed service calls, private projections and revision refresh | Reuses existing engine services and command keys; never accepts browser permission claims as authority |
| Engine/services/database | Rules, campaign binding, ownership/consent, revisions, dice, atomic events, state and durable jobs | One authoritative campaign store; existing release gates and events remain |
| Discord bot/worker adapter | Gateway, Activity entry point, server provisioning, nickname/role sync, chat permissions, approved receipts/notices and fallback controls | Discord effects follow committed engine work; removing slash UI must not stop required workers |

The backend and bot may initially be separate modules in one managed application.
A separate host/service is not necessary to establish the boundary. Do not share
SQLite across a network or introduce another authoritative copy of the campaign.

## Current implementation findings

- Pure creation document parsing and HTML serialization already exist. Reuse the
  v1 schemas/catalog rather than implementing rules independently in the UI.
- `CharacterTransferService`, profile/creation services and `GameService` already
  accept service inputs rather than Discord interaction objects.
- `GuildViewer` is currently declared in `services/read_only_bot.py`, and shared
  policy lives in `discord_adapter/config.py`. These names/import locations are
  residual coupling, not a reason to move or rename hundreds of consumers now.
- `ReadOnlyDiscordBot` currently constructs services, registers UI and starts
  nickname sync, receipt delivery, source-pause, game and facilitator workers.
  The worker lifecycle must remain explicit during any UI isolation.
- v0.1.4 import/export remains the source-proved first backend consumer. No HTTP
  routes, web session validation or browser connection are implemented here yet.

## Bounded first work package: Activity-backed character drafts

Dependency: Activity task supplies repository/branch/commit, framework, backend
layout, authentication flow, deployed origins/proxy setup and current API/client
contracts. Coordinate file ownership before either task changes shared contracts.

Normal flow: verified Activity session → authorized own draft/sheet read → edit
starting choices → private engine preview → explicit confirm → atomic engine save
→ refresh the actual saved draft and remaining creation requirements.

1. Reconcile that handoff with current HarpyEngine and the existing JSON adapter.
   Use the Activity's actual server framework if one exists; do not select a new
   framework speculatively.
2. Add a narrow server adapter for the catalog, own template/sheet projection,
   import preview and explicit confirmation. Reuse `CharacterTransferService`.
   Endpoint names and session transport are to be agreed against the real UI.
3. Establish the principal from server-verified Discord authentication and current
   membership/roles. Bind it to the permitted guild/campaign; verify relevant
   channel/instance context server-side where required. Do not trust user IDs,
   administrator flags or authorization claims supplied by the browser.
4. Keep previews server-held, owner/campaign/digest/context/revision bound, with
   expiry and stable retry outcomes. A posted JSON preview is not authority.
   Retain existing atomic rollback and stale-state checks.
5. Return only the authorized projection. Personal notes require explicit owner
   inclusion. Cross-account/Handler access must not expose private Pilot data.
6. Update the UI from engine results; begin with a bounded refresh/read path.
   Shared participant state must not broadcast private choices or draft content.
7. Leave native controls and the running v0.1.4 release available until this
   vertical workflow passes synthetic integration and genuine human testing.

Use the existing native/source services for later review, activation and consent;
this first package does not reimplement those workflows in a browser. Do not
automatically activate characters or accept agreements to simplify the UI.

Completion evidence: one synthetic native/Activity document round trip preserving
the same saved choices; authenticated owner read/save/reopen; wrong-owner/public
privacy rejection; stale preview rejection; same-key retry without duplicate
writes; known failed application rolls back. Run focused affected checks and
changed-source static checks. No broad regression or new combinatorial matrix
is needed merely to write the adapter. Actual Activity login and human setup
remain separate acceptance evidence.

## Subsequent whole workflows

1. Move remaining creation coordination/review/activation UI once its actual
   next-decision-owner and privacy semantics are represented end to end.
2. Move requests and choice resumption as one resumable workflow, preserving
   private visibility, ownership, revisions and durable pending work.
3. Move ordinary Play selection/preview/confirmation and actual consequences;
   preserve engine dice, costs, receipts and pending chat holds.
4. Extract the bot composition/worker lifecycle only where those delivered
   consumers demonstrate the shared dependency. Keep the Discord gateways and
   durable jobs intact; do not disable workers while hiding slash commands.
5. Make the Activity the advertised default after human acceptance. Retain an
   entry point, independent OOC safety/admin recovery and required fallbacks.
   Inventory old component callbacks and in-flight work before removing controls.

## Deployment and scope

This contract authorizes preparation; it records no implemented HTTP API, new
authentication or Activity deployment. The last owner-authorized live runtime is
v0.1.4 at `fe47d7ef0b558a1106f5dc48b25c277aff5f875b`; check the private deployment
record for actual process state. No restart, command removal, campaign migration,
environment publication, AI call or expanded gameplay approval accompanies this
document. Preserve the source-pinned release while development proceeds.

## Handoff requested from the Activity task

Provide a concise current-state handoff containing:

- Repository URL, branch, exact commit and relevant local/source paths.
- Frontend framework, Embedded App SDK integration and Activity launch setup.
- Backend framework and deployment, existing endpoints and client request types.
- Current Discord authorization/session flow and how guild context is verified.
- Whether state is local/demo, file-exchanged or backed by a live authority.
- Active assignments/files, tested behavior and remaining blockers.

Keep secrets, tokens and private campaign data out of the handoff.
