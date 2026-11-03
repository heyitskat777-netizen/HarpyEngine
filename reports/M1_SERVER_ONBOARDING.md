# M1 server setup and draft onboarding acceptance

**Status: automated checks PASS; live administrator setup/onboarding verification PENDING.**
**Scope:** owner-requested M1 additions. Full original M1 and rules-certified
character creation are not complete. M0 and earlier read-only M1 evidence remains
historical and unchanged.

## Delivered

- Additive project roadmap, explicit M1A server setup, M1B draft onboarding and
  M2 full-character-builder work orders. Original handoff is untouched.
- Acceptance registry with 16 executable M1 cases and 4 future builder cases
  explicitly NOT_RUN. Every automated mapping names an existing executable test.
- Explicit migration `0001` for seven metadata tables: campaign binding, membership,
  drafts, idempotent command inbox, audit events, setup plans and resource mappings.
- Administrator `/server setup` preview and ten-minute, actor/guild-bound confirm.
  Template creates two categories, seven text channels and one entry message.
  Both preview and apply check authorization; apply checks bot permissions again.
- Persistent mappings, serialized resource reservation and resumable known failures.
  Unknown API outcomes and missing/drifted managed resources stop for review, with
  no name-based adoption, duplicate retry or unrelated channel overwrite.
- Persistent new-player buttons, explicit self-join, private draft form, private
  review/save confirmation, stable character IDs, revision checks and `/sheet`.
- Backend public/private projections: another administrator gets only the public
  sheet. Private notes are absent from generic audit/inbox outcomes. Responses
  disable mentions and bound escaped output to Discord's message limit.
- No role creation, no global setup command, no Administrator bot permission,
  no channel-history reading. Single configured private guild per process.

## Evidence

See [validation output](M1_SERVER_ONBOARDING_VALIDATION.txt) and
[acceptance case mappings](../docs/acceptance/server_onboarding.json).

| Check | Actual outcome |
|---|---|
| Offline executable tests | **92 passed; 0 failed, 0 skipped, 0 xfailed** |
| Ruff lint / format | Passed; 56 Python files formatted |
| Strict mypy | No issues in 34 application source files |
| Migration | Fresh/repeated upgrade, check and downgrade pass on synthetic databases |
| Live metadata DB | Backed up before additive upgrade; metadata check reports no new operations |
| Draft persistence | Stable IDs/revisions and private notes survive reconstructed service; stale/concurrent saves cannot overwrite |
| Request retry | Same interaction/payload returns stored outcome; changed payload conflicts |
| Isolation | Wrong guild, same campaign rebound to another guild, same-name characters in two campaigns and another user's save button tested |
| Setup retries | Restart/repeat, concurrent confirmations, clear partial refusal and unknown create outcome tested |
| Staff area | @everyone view denied, bot view allowed; no PC notes posted there |
| UI | Persistent entry IDs, owner form resume, bounded sheet rendering, private save ownership and UI rate limits tested |
| Packaging | Offline build passed; wheel 38 entries, source distribution 116 entries including migration; private assets excluded |
| Original handoff | Validator passes; 40/40 manifest hashes/sizes unchanged |
| Private engine | 120/120 original template hashes unchanged |
| Live registration | Seven top-level commands/groups read back; Gateway READY observed |
| Graceful process restart | SIGTERM closed prior process with exit 0; updated process became ready |
| Live permission preflight | Bot initially lacks Manage Channels; administrator action requested |
| Live create/save interaction | Pending; not counted as passed from offline or registration checks |
| Remote CI | Workflow available; current remote outcome not yet observed |

## Boundaries and remaining work

Confirmed saves persist; unsubmitted forms and unconfirmed previews do not.
Persistent entry buttons and slash fallbacks restore access after process restart.
The setup plan is stored, but expired or pre-restart ephemeral confirmations must
be reopened. A deleted entry message is not reposted automatically: its ID is
reused without reading message history; slash fallbacks remain available.

This is a **draft sheet**, not a fully rules-validated playable character. The
wizard records proposed labels and notes; no numeric stats, legal combinations,
mechanical effects or official rules are invented. The full builder work order
requires source audit and independently verified activation before gameplay.

Original M1 dice, full gameplay event replay, durable outbox, backup/restore
operations and engine transaction adaptation remain unfinished. Metadata audit
omits private data and is not a complete character-rebuild journal; retain the
SQLite database/backups. No raw engine roll/finalize command is called. Membership
revocation/campaign administration and multi-guild self-service activation remain
later work. Creating a bot invite alone does not activate this app on arbitrary
servers; trusted per-guild configuration is required in this private pilot.

Bot tokens, actual user IDs/drafts, runtime policies, database/backups, canonical
campaigns, GM notes and PDFs remain outside Git. No environment was published.
No Discord resources were created by the agent directly; the administrator must
explicitly confirm the in-bot preview. The bot remains available in this session.

## Diagnosis and review

SQLite `BEGIN IMMEDIATE` serializes metadata writers; no transaction spans an HTTP
request. Resource claims precede Discord creation, acknowledgements persist IDs,
and uncertain outcomes halt. Clear Discord 4xx refusals reset a pending resource
for a later retry. Per-process apply lock plus DB state protects double confirms.

Security review found and closed a potential misconfiguration leak: reads and
setup confirmations now verify the stored guild/campaign binding, not only the
configured ID. Cross-guild rebinding has a regression test. User-authored labels
are validated, escaped, and shown only in typed projections; no raw state/exception
is sent to a channel. UI throttling is bounded/process-local and not authorization.

Some legacy empty-scaffold assertions were updated for the reviewed M1 migration.
Initial formatting/type issues were corrected before final passing checks. Future
rules-builder acceptance cases remain NOT_RUN; original 86 planned cases and the
private engine's earlier 66-test baseline are separate from these 92 tests.

## Changed files

- `AGENTS.md`
- `README.md`
- `docs/PROJECT_ROADMAP.md`
- `docs/acceptance/server_onboarding.json`
- `docs/work_orders/M1A_SERVER_SETUP.md`
- `docs/work_orders/M1B_CHARACTER_ONBOARDING.md`
- `docs/work_orders/M2_CHARACTER_BUILDER.md`
- `migrations/env.py`
- `migrations/versions/0001_server_onboarding.py`
- `pyproject.toml`
- `reports/M1_SERVER_ONBOARDING.md`
- `reports/M1_SERVER_ONBOARDING_VALIDATION.txt`
- `src/girlframe/__init__.py`
- `src/girlframe/__main__.py`
- `src/girlframe/database/base.py`
- `src/girlframe/database/tables.py`
- `src/girlframe/discord_adapter/bot.py`
- `src/girlframe/discord_adapter/config.py`
- `src/girlframe/discord_adapter/onboarding.py`
- `src/girlframe/discord_adapter/runtime.py`
- `src/girlframe/engine/drafts.py`
- `src/girlframe/services/onboarding.py`
- `src/girlframe/services/provisioning.py`
- `src/girlframe/services/read_only_bot.py`
- `tests/test_database.py`
- `tests/test_onboarding.py`
- `tests/test_read_only_bot.py`
