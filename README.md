# HarpyEngine — GIRL FRAME private Discord pilot

M0 is accepted. M1 now implements server setup, persistent owner-bound drafts,
Girl/Frame dropdowns and Discord tags, raw OS-backed 2d6 receipts, a filtered ledger,
OOC safety pauses, retryable public delivery, and local backup/restore/rebuild tools.
Offline acceptance and live verification are tracked in
[reports/M1_ACCEPTANCE.md](reports/M1_ACCEPTANCE.md). The owner confirmed the dice,
receipt/ledger, publication and safety smoke tests. This is not a production
readiness claim.

M2 has started with `/character build`: source-backed starting Identities, Asset
choices and appearance, saved privately with revision history. Playbook details
now include Vatgrown DNA basis and Prince fanbase demographics/demanded/rejected
qualities, including custom choices. JANUS-B uses official
JANUS rules and retains its server label. See [M2 evidence](reports/M2_ACCEPTANCE.md).

Characters remain **drafts / rules unverified**. Official Plays, modifiers, Heat,
mechanical consequences, AI and recovered-engine writes are deferred. M1 raw dice
are a test primitive and never resolve a GIRL FRAME Play.

Read `AGENTS.md` and [the roadmap](docs/PROJECT_ROADMAP.md) before development. The
original planning package remains unchanged in `GIRLFRAME_Discord_Codex_Handoff_v0.2/`;
its historical `planning/` paths refer to that directory.

## Install and check

Use Python **3.12.14**, **uv 0.12.23** and the committed lockfile. On a new machine,
install that Python and `python -m pip install uv==0.12.23`. From the repo root:

```bash
bash tools/install.sh
source .venv/bin/activate
python -m girlframe --help
python -m girlframe health
```

The installer runs `uv --cache-dir .cache/uv sync --locked --all-groups`. It does
not migrate data or start services. Health checks local SQLite, not live Discord
readiness. `.env` is not auto-loaded. `GIRLFRAME_DATABASE_URL` defaults to
`sqlite:///./var/girlframe.db`; only plain local SQLite URLs are supported. Run
from the repository root. Keep databases, backups and policy under ignored `var/`
or outside Git. Never delete a populated database to refresh the environment.

Before upgrading an existing database, make a new private backup, then migrate:

```bash
python -m girlframe db backup --dest var/backups/before-0005.db
python -m alembic upgrade head
python -m alembic check
```

For a fresh database, skip backup and run migration. Startup refuses missing schema
and never migrates automatically. Migration `0003` adds the ledger and captures the
current revision of older drafts as a private baseline; earlier overwritten draft
revisions cannot be recovered. Existing campaigns, channels, roles and drafts are
preserved. Migration `0004` adds private append-only creation progress without
rewriting existing records. Migration `0005` adds immutable private Bond proposals. `alembic downgrade base` destroys application tables: use only on
throwaway test databases. Never downgrade real campaign data to roll back code.

## Discord application and startup

This Gateway pilot activates **one configured guild per process**, with no global
commands. Install the application with `bot` and `applications.commands` scopes.
Supply the raw bot token only through secure environment variable **`DiscordBot`**.
Never put it in policy, source, commands or logs. The application public key is not
used by Gateway mode; do not configure a competing HTTP interactions endpoint.

View Channels and Send Messages support commands and explicit ledger delivery.
Setup additionally needs Manage Channels. Character tags need Manage Roles and
Manage Nicknames, with the bot's role above label roles and members it should
rename. Read Message History is optional for bounded delivery reconciliation in
the managed ledger. No Administrator bot permission or privileged intents are
required. Changing portal default install permissions does not update existing
server role grants automatically.

For the owner's private test guild, create the synthetic policy once:

```bash
python tools/setup_discord_dev.py \
  --application-id 1566951910601269268 \
  --guild-id 1566954229535608913 \
  --approve-admin-status
python -m girlframe start --config var/discord-dev/policy.json --check
bash tools/run_discord_dev.sh
```

Setup refuses an existing destination; retain and reuse the policy. Its sandbox
is a synthetic **read-only engine-status fixture**, not a runnable game engine.
Policy examples are in `config/discord-policy.example.json`. The offline `--check`
validates policy/sandbox only, not schema, credentials or live guild access.

Actual startup checks the authenticated application and guild, then synchronizes
11 top-level commands/groups in that guild only. Reconnect does not resync commands
or duplicate workers. Responses are ephemeral, with mentions disabled. Only an
explicit confirmed setup posts onboarding controls; only `publish:true` on a roll
queues a public receipt. SDK DEBUG logging must stay disabled because it can
include interaction credentials. HTTP/Gateway use the inherited HTTPS proxy and
verified TLS. SIGTERM and Ctrl-C close the bot.

A process in a development session is temporary hosting and must be restarted after
environment restoration. This work does not publish environment configuration.
HTTP 404 / Discord 10004 at startup means the application cannot access the guild:
check installation and guild ID. Errors omit raw provider bodies and private paths.

## Commands and player flow

| Command | Access and behavior |
|---|---|
| `/help` | Configured guild member; private usage |
| `/health` | Explicitly enabled guild administrators; local service/sandbox check |
| `/server setup` | Configured administrator; preview, then caller-bound confirmation |
| `/campaign create name` | Configured administrator; initialize once without resetting data |
| `/campaign join` | Explicit self-enrollment as a player |
| `/campaign status` | Joined member or configured administrator; stored M1 status |
| `/campaign_status` | Stored M1 status alias, retaining the earlier approved audience restriction |
| `/character create`, `/girl create` | Joined player; own dropdown draft wizard |
| `/character build` | Joined owner; private starting Assets, Identities and appearance; save/reopen progress |
| `/character bond member` | Joined player; privately review and confirm a starting Bond proposal |
| `/character bonds [before]` | Participants only; resume saved proposals and accept/decline/withdraw |
| `/character sync` | Retry your saved label roles and nickname |
| `/sheet [member]` | Joined player; own private sheet or another member's public sheet |
| `/roll basic [publish]` | Joined owner with saved draft; raw 2d6, published by default; `publish:false` keeps it private |
| `/roll show receipt` | Own private or campaign-published receipt only |
| `/ledger [before]` | Joined player; permitted events, eight per page |
| `/safety pause` | Joined participant; save their own OOC pause, without a reason |
| `/safety resume` | Clear only your own pause; other pauses continue blocking rolls |

DMs, wrong guilds, nonmember identities and inactive campaign membership are denied
server-side. Admin status never authorizes reading another player's private notes
or private receipts. Ownership comes from authenticated numeric IDs, not names,
Discord tags, slash options or claims in messages. Players cannot select arbitrary
campaigns, files, channels or another roll actor. The bot does not consume passive
roleplay transcripts or interpret edited messages as state changes.

Run `/server setup`, review the layout, and confirm within ten minutes. It creates
two categories, seven text channels, and reusable new-player controls. Public
welcome/directory/mission/ledger channels are read-only to ordinary members. Staff
resources deny @everyone visibility. Backend secrets are never posted in staff
channels. Setup saves resource IDs, resumes known partial results, checks permission
drift and never adopts unrelated same-name channels. An ambiguous create pauses
for operator review to avoid duplicates; no teardown command deletes channels.

In `new-players`, join and choose **Create/Edit draft**. Choose Girl and Frame from
dropdowns; enter callsign and optional private notes, review, then **Save draft**.
Only confirmed saves persist. Stable IDs and revisions survive restart. Stale forms
cannot overwrite newer saves. Unsubmitted forms expire; reopen to continue from the
last saved draft. Persistent entry buttons are restored at startup; slash fallbacks
remain available if the entry message is deleted.

Saving queues the Girl/Frame label roles and callsign nickname. SORROW + Mockingbird
+ JANUS-B requests **MOCKINGBIRD**, **JANUS-B** and **SORROW**. Only app-owned,
permission-free label roles are managed; unrelated roles are preserved. A blocked
Discord update leaves the draft saved and can be retried. Discord forbids renaming
the server owner; that test account must set its own nickname manually. Other
hierarchy and permissions restrictions also apply. JANUS-B is an owner-requested
server label using official JANUS rules, as confirmed by the owner. See
[character tags](docs/CHARACTER_TAGS.md).

After saving the profile, use `/character build` to select two Girl Assets and two
Frame Assets, describe them, and fill in appearance/Frame name. Mockingbird chooses
one selected Girl Asset as Void-altered. Wyvern's Enormous is additional. Bonded's
Girl Asset selection waits for a Pair-authorized relationship workflow. Starting
Identities are derived from the official playbook. **Save progress** persists a
partial form; reopen the command after a timeout or restart to continue. Unsaved
edits are temporary. Saving changed Girl/Frame playbooks starts new choices while
retaining earlier private history. Creation details are currently available only
through this owner-only builder; `/sheet` still shows the M1 profile. Bonds, Status,
special resources, independent review and playable activation remain unfinished.

Use `/character bond member` to choose another player from Discord's member picker,
select a starting playbook prompt and review optional context shared with that
player. Confirm saves a pending proposal. The recipient opens `/character bonds`,
chooses it from a dropdown and accepts or declines. Either participant can withdraw
an accepted setup agreement; a source can cancel a pending proposal. No DM or public
notification is sent. Reopen the command after timeout/restart to resume saved
proposals. Unsubmitted forms expire after ten minutes. Private listings show up to
20 proposals, with a `before` cursor for another page; IDs determine page order.

Most Girl branches propose Personal Bonds; Bonded proposes an Intense Pair Bond.
AM's review explicitly tells the counterpart she is Jailbroken. Newgirl's Mentor
must be assigned by the Handler, so her starting proposal is blocked with
`UNSUPPORTED_RULE` until that workflow exists. Both profiles must be saved and both
members active. Any profile revision change makes old agreement/proposal data stale;
withdraw or decline it and make a new proposal. Duplicate live outgoing proposals
and duplicate live proposals between the same pair are rejected. Accepted proposals
remain draft setup agreements; NPC Bonds, Handler assignment, Pair Assets and full
creation validation remain pending. Private context/history stays in the database
and backups, outside public sheets, exports and ledger payloads.

A raw roll returns two faces, their sum, timestamp and stable receipt ID. It changes
no character resources. `/roll basic` defaults to `publish:true`, queuing the receipt
to the managed `rolls-and-ledger` channel. Use `publish:false` for a private roll.
Delivery failures retry without rolling again. Existing saved
receipts remain retrievable while paused. `/campaign status` reports the **bot's
stored M1 campaign**, independent of the recovered engine's paused turn counter.

Ordinary metadata and ledger commands have bounded per-user throttles. OOC safety
pause bypasses that throttle and does not lose a race to unrelated revisions.
Resume clears the caller's request only. No fictional penalty or reason is recorded.

## Persistence and recovery

SQLite WAL is the authority for M1 metadata and raw receipts. The recovered engine's
canonical JSON is not imported, synchronized or modified. The schema has principals,
campaign membership, drafts, command inbox, append-only events/snapshots/receipts,
setup resources, managed roles, tag jobs, safety pauses and a transactional outbox.
Numeric Discord IDs remain membership natural keys; principals additionally have
stable UUIDs. See [M1 ledger design](docs/M1_LEDGER.md).

Each raw roll transaction checks membership, expected campaign revision, pause and
own draft before sampling OS randomness. It commits one receipt, two distinct
indexed events, the command outcome and optional outbox together. An identical
interaction retry returns that receipt, including after restart; changed semantic
payload conflicts. Expected revision is a first-execution precondition, not part of
the roll's semantic hash, so refreshed retries still retrieve the original receipt.
A stale new command samples no dice. Failed transactions expose no receipt.

Delivery is **at least once**, not externally exactly once. Durable leases and claim
tokens prevent ordinary concurrent sends and stale acknowledgements. Retries reuse
a nonce and, with Read Message History, reconcile the last 50 posts in the managed
ledger by bot author and receipt marker. Missing history permission, an older post,
or an acknowledgement race can produce duplicate messages. Each shows the same
saved receipt; delivery never creates another roll or game event. Reconciliation
never scans roleplay channels. Discord edits/deletions do not change stored records.

Trusted local maintenance (not player commands):

```bash
python -m girlframe db backup --dest var/backups/pilot-unique.db
python -m girlframe db restore --source var/backups/pilot-unique.db --dest var/restored.db
python -m girlframe db export --config var/discord-dev/policy.json --dest var/public-export.json
python -m girlframe db rebuild --config var/discord-dev/policy.json
python tools/seed_synthetic.py --dest var/offline-synthetic.db
```

Backup uses SQLite's backup API, includes committed WAL data, and verifies integrity
and foreign keys. Backups contain private data and are created mode 0600. Restore
always creates a **new offline file**, refusing any existing destination. Stop the
bot before deliberately switching `GIRLFRAME_DATABASE_URL` to a verified restore;
keep the old database and policy. Restored pending outbox work may retry delivery.
Public export excludes notes, private receipts and actor/membership IDs. It is a
view, not a full restore source. Export and seed also refuse existing destinations.

Rebuild restores current character public/private projections from immutable
versioned snapshots, and appends local-operator audit provenance; it neither rolls
nor changes recorded receipts/events. It does not reconstruct setup IDs, membership,
safety or delivery operational state from text events; use a full backup for those.
The old pre-0003 draft baseline is explicit, not invented historical revisions.
Run backup before repair. Synthetic seed creates a separate fresh offline DB with
fixed fake identity IDs, one draft and one real OS dice test; do not run it as a live
server database.

## Recovered engine reference

The full private engine and PDFs remain outside Git. The reviewed read-only bridge
reads only strict `turn` and `paused` fields from an explicitly selected disposable
sandbox, without importing/executing private scripts. Configure a trusted absolute
`GIRLFRAME_ENGINE_SANDBOX`, then `python -m girlframe engine-status`. The source must
have the noncanonical marker, `scripts/gm.py` and `state/campaign.json`; symlinks,
malformed types and snapshots over 4 MiB are refused. No sandbox is auto-discovered.

The corrected private package was independently checked with `package_probe.py`,
`verify_engine.py --require-full`, `bootstrap_dev.py`, and its runtime `gm.py validate`.
See [engine inventory](docs/ENGINE_SOURCE_INVENTORY.md). That verification is separate
from bot acceptance and does not certify every mechanic. No v1.3.11 implementation
is claimed. Never run a mutating command against its packaged canonical template.

## Validation and limits

```bash
ruff check .
ruff format --check .
mypy
pytest -q
python GIRLFRAME_Discord_Codex_Handoff_v0.2/verification/verify_handoff.py
python tools/check_repository.py
```

Tests use synthetic data and block outbound network. They cover migrations, private
views, IDs, two-campaign isolation, real SQLite concurrency, fixed injected test RNG,
commit/delivery crash points, restart replay, immutable records, backup/restore,
projection rebuild and fake Discord interactions. Production has no seeded RNG
configuration. In this managed shell, pytest needs supported command escalation
for asyncio worker-thread wakeups; its network block stays enabled. CI performs
offline checks, not live Discord tests. Coverage percentage is not measured.

The historical 86-case catalogue is unchanged; current test mappings are additive in
`docs/acceptance/`. Full rules-certified creation and M2 Plays require a separate
source audit and acceptance. Multi-guild self-service, continuous hosting, retention/
erasure workflows and production security remain unfinished. SQLite and in-process
workers are a private single-writer pilot design. Immutable private draft snapshots
are sensitive history; multi-user release needs a retention policy first.

## Rights and private references

Private development grants no open-source license. GIRL FRAME is authored by
Isabelle M. Ruebsaat; the game, official sheets, names and other third-party material
retain their respective rights. This project does not assert affiliation or relicense
them. Dependencies retain their own licenses. Do not commit official PDFs, private
engine archives, campaign saves, real messages or credentials. `.gitignore` is an aid,
not permission to force-add private material.
