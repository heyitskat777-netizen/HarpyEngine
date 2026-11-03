# HarpyEngine — GIRL FRAME read-only Discord bot

M0 is accepted. M1 includes the guild-scoped status bot, administrator-confirmed
server setup, explicit campaign joining and saved owner-bound character drafts.
No rolls, recovered-engine writes, AI or rules-certified characters are enabled.
The broader M1 ledger/dice work is not complete. Current work orders and acceptance
cases are indexed in [PROJECT_ROADMAP.md](docs/PROJECT_ROADMAP.md).

Read `AGENTS.md` first when developing. The original planning handoff remains in
`GIRLFRAME_Discord_Codex_Handoff_v0.2/`; its `planning/` references refer to that
directory. The owner authorized M1 server setup and draft onboarding; stop before
recovered-engine writes, official Plays or AI.

## Install

Use Python **3.12.14** and **uv 0.12.23**. Both are available in the prepared cloud
environment. On another machine, install Python 3.12.14 and use
`python -m pip install uv==0.12.23`. From the repository root:

```bash
uv --cache-dir .cache/uv sync --locked --all-groups
source .venv/bin/activate
python -m girlframe --help
python -m girlframe health
```

The same install command is saved in `tools/install.sh`; run `bash tools/install.sh`
to create or refresh the development environment. It does not start services.

The local cache location supports cloud machines with read-only home directories.
`uv.lock` pins transitive dependencies and hashes. Do not regenerate the lock as
part of normal installation. Python is constrained to 3.12 for this tested M0
baseline; widen support only with validation. Offline checks need no token. The recovered
private engine supplies its own bootstrap/verification tools outside this checkout;
see [engine source inventory](docs/ENGINE_SOURCE_INVENTORY.md).

`health` executes a local SQL query and reports `discord_connected: false` and
`rules_implemented: false`. Health success is not live bot/game readiness.

## Run the read-only Discord bot

Use the private test guild only. In the Discord Developer Portal, install this
application with `bot` and `applications.commands` scopes. View Channels and Send
Messages are sufficient for this test bot; do not grant Administrator. No
privileged message-content, member-list or presence intents are used. This bot
uses the Gateway, not an HTTP interactions endpoint; its public key is not needed
by this runtime. Do not configure a competing HTTP interactions endpoint.

Supply the raw bot token through the secure environment variable **`DiscordBot`**.
Do not put it in policy JSON, source, commands, screenshots or logs. `.env` files
are not auto-loaded. The runtime preserves the inherited HTTPS proxy for Discord
REST and Gateway traffic and keeps TLS verification enabled.

For a reproducible synthetic test (no private campaign required), from the root:

```bash
source .venv/bin/activate
python tools/setup_discord_dev.py \
  --application-id 1566951910601269268 \
  --guild-id 1566954229535608913 \
  --approve-admin-status
python -m girlframe start --config var/discord-dev/policy.json --check
bash tools/run_discord_dev.sh
```

Setup refuses an existing destination. On subsequent starts, reuse the policy;
do not rerun setup or delete a configured sandbox to reset it. The generated
`sandbox` is a **status-only synthetic fixture**, not a runnable game engine. It
reports turn 0, paused. The real private engine remains external and unchanged.

`start --check` validates policy and readable sandbox offline without a token.
Actual startup verifies token/application identity and access to the configured
guild, then registers seven top-level commands/groups **in that guild only**. Sync replaces
this application's command set in that test guild; no global command sync occurs.
Gateway reconnects do not re-register commands. `Ctrl-C` and SIGTERM close the
client. Processes must be restarted after environment restoration/publication.

All replies are ephemeral with mentions disabled. Authorization runs server-side:

| Command | Access |
|---|---|
| `/help` | Authenticated members of the configured guild |
| `/campaign_status` | Explicit `status_user_ids`, or guild administrators if enabled, with audience approval |
| `/health` | Guild administrators only, and only when explicitly enabled by policy |
| `/server setup` | Configured administrator; preview and caller-bound confirmation |
| `/campaign join` | Guild member explicitly joining as themselves |
| `/character create` | Joined player; create or resume their own draft |
| `/sheet [member]` | Joined player; own private sheet or another member's public sheet |

DMs, wrong guilds, and users without guild-member proof are denied before snapshot
access. Roles are derived from Discord's member permissions, never display names
or slash options. There are no player-supplied path/campaign selectors. SDK command
visibility is supplementary; changing Discord command permissions does not bypass
backend checks. Status commands have a per-user/guild cooldown of three uses per
ten seconds; setup previews have a ten-second per-user/guild cooldown.

The local JSON policy persists membership/access settings across process restarts;
changes require restart. See `config/discord-policy.example.json`. It is a trusted
operator configuration, not a public API. Store real rosters under ignored `var/`
or outside Git. The generated development policy deliberately approves status
only for test-guild administrators; ordinary members are denied until their
numeric Discord IDs are added to `status_user_ids`. This is read-only access, not
permission to act for any player character.

To select an actual disposable engine runtime later, set the policy's `sandbox`
to its absolute path and review audience approval. Do not point it at canonical
state. `GIRLFRAME_ENGINE_SANDBOX` controls the separate local `engine-status` CLI;
the live bot reads only the sandbox bound in its policy. Do not enable SDK DEBUG
logging; it may include interaction credentials.

If startup reports `404/10004`, Discord cannot see that guild: install the bot or
verify the server ID. Invalid credentials, permission failures and other errors
produce sanitized messages. No response bodies, raw state or private paths are
printed to users. Only an explicitly confirmed setup publishes the generic
new-player entry message; no unsolicited gameplay or roleplay messages are sent.

## Server setup and character onboarding

Run `python -m alembic upgrade head` explicitly before starting this version.
Back up existing SQLite data before upgrading; installation and bot startup do
not run migrations automatically. Startup refuses an unmigrated database.
The local policy/snapshot `--check` remains an offline configuration check, not a
database migration or live Discord readiness claim.

Grant the bot **Manage Channels**, View Channels and Send Messages for provisioning;
do not grant Administrator. Server setup itself creates no roles. Character label
assignment additionally needs **Manage Roles** and **Manage Nicknames**, with the
bot's role above its labels and members it should rename.
An administrator invokes `/server setup`, reviews the versioned layout, then
confirms within ten minutes. Preview creates no Discord resources. Confirmation
is bound to that administrator and campaign, and rechecks bot permissions.

The template creates two categories and seven text channels, then posts reusable
new-player controls. Welcome, character directory, mission board and rolls/ledger
are read-only to ordinary members. Staff category/review deny @everyone visibility.
Reserved mission/scene/ledger channels do not imply gameplay is implemented.

This private-pilot version serves one explicitly configured guild per process.
Joining another server does not activate it there or create channels automatically;
that server needs a trusted guild/campaign policy first. Multi-guild self-service
installation is a later deployment extension, not a global command enabled here.

Resource IDs are persisted. Repeat or restart reuses known IDs and resumes known
partial failures, without adopting same-name unrelated channels. Existing managed
permission drift or deleted resources stops for administrator review; nothing is
silently overwritten. An ambiguous create response pauses to avoid duplicates.
Saved own-message IDs are reused without acquiring Read Message History or reading
transcripts; a deleted onboarding message requires repair, while slash fallbacks
remain available. No automatic teardown/delete command exists.

In `new-players`, choose **Join campaign**, then **Create/Edit draft**. Choose Girl
and Frame from dropdowns, then Continue to enter callsign and optional private
notes. Review the private preview and press **Save draft**. **My sheet**, `/sheet`,
and `/character create` retrieve that same saved character and stable ID. Reopen
the form to edit/resume; old forms cannot overwrite newer revisions. Repeating
the same submitted interaction returns its original result, not another character.
Only confirmed saves persist. Unsubmitted forms and unconfirmed previews expire
and must be reopened; persistent entry controls restore after the bot restarts.
Interactive metadata actions are limited to three per ten seconds per guild/user;
this process-local throttle resets on restart and does not replace authorization.

Saving also queues the selected Girl/Frame Discord label roles and uses the
callsign as server nickname. For example, SORROW + Mockingbird + JANUS-B requests
roles **MOCKINGBIRD**, **JANUS-B** and nickname **SORROW**. Only app-owned, permission-free
roles are created/reused; unrelated roles remain untouched. `/character sync`
retries your own request, and pending jobs resume in the background after restart.
The draft remains saved even if a Discord change is denied. A bot cannot rename
the server owner, and hierarchy restrictions still apply; the private result
explains a blocked or pending change. See [character tags](docs/CHARACTER_TAGS.md).

These are **drafts / rules unverified**, not mechanically playable official sheets.
Dropdown names are verified, but no stats or legal combinations are invented.
JANUS-B is an owner-requested server label of JANUS, not a separate rules claim.
The full verified builder
has its own work order and NOT_RUN acceptance cases. Private notes appear only to
their owner through the application, even when another administrator requests a
public sheet. Long escaped notes are truncated in Discord display but retained
for owner editing. Discord messages are views; SQLite owns these metadata records.
The private engine's canonical JSON is neither imported nor changed.

Campaign joining and draft ownership are database-backed. The existing status
command retains its separate approved-user/admin policy; joining does not silently
grant additional status or administrator permissions. Actual policy, member IDs,
drafts and backups stay under ignored `var/` or outside Git. A human server admin
can see Discord's staff area; that does not confer access to another PC's notes.

## Read-only engine integration

M0 now includes a reviewed copy of the v1.3.10 read-only bridge and a local
`engine-status` service/CLI. This code is installed by the normal locked setup;
it does not import or execute the private engine's Python scripts. No private
archive is required for the synthetic CI suite.

Keep the supplied PRIVATE archive outside the checkout. From its extracted root
(containing its own `AGENTS.md`), follow its private setup instructions:

```bash
python tools/package_probe.py
python tools/verify_engine.py --require-full
python tools/bootstrap_dev.py
python runtime/dev/scripts/gm.py validate
```

Bootstrap creates a disposable runtime with a noncanonical marker and refuses to
overwrite an existing destination. Do not run mutating commands against the
packaged canonical template. Back in this application's root, configure the
absolute location of that disposable runtime:

```bash
export GIRLFRAME_ENGINE_SANDBOX=/absolute/private/path/runtime/dev
python -m girlframe engine-status
```

Output contains exactly `turn` (nonnegative integer) and `paused` (boolean). These
fields still need GM approval for their audience before Discord exposure. The
command does not create a DB, write state, launch the engine, or call Discord. No
path option can be supplied by a player; only trusted local configuration selects
the sandbox. Without configuration it exits 1; it never searches for campaign data.

The source must have the bootstrap marker, `scripts/gm.py`, and `state/campaign.json`.
The adapter rejects symlinked roots, scripts/state directories, or required files,
invalid status types, malformed JSON and snapshots larger than 4 MiB. The marker
is an accident-prevention check, not cryptographic proof of isolation. Use a
trusted local sandbox and filesystem; M0 does not guarantee consistent reads while
another process is rewriting files. Errors omit underlying paths and raw data.
Public-facing Discord commands and user/campaign authorization remain M1 work.

## Validate

After activation, run these commands from the repository root (CI uses the same
tools through `uv run --no-sync`):

```bash
ruff check .
ruff format --check .
mypy
pytest -q
python GIRLFRAME_Discord_Codex_Handoff_v0.2/verification/verify_handoff.py
python tools/check_repository.py
```

Tests use synthetic data and block in-process network connections. They exercise
identity validation, the service/fake-transport seam, CLI success/failure paths,
SQLite WAL and foreign keys, and repeatable empty migration setup. No live Discord
or model integration is tested. Engine-status tests also verify allowlisting,
strict types, sandbox selection, bounded reads and byte-for-byte nonmutation with
synthetic files. The historical 86-case catalog remains NOT_RUN;
it is not the executable M0 suite. Coverage percentage is not currently measured.

M1 tests also cover the Discord command surface, permission matrix, private
deferral/response transport, strict policy, app/guild checks, restart configuration,
cooldowns and sanitized failures. In the managed command sandbox, asyncio worker
thread wakeups may be blocked; run pytest with supported command escalation when
needed. Its network-blocking fixture remains enabled, so these are offline tests.
Python 3.12's known discord.py `audioop` import deprecation is narrowly filtered;
all other warnings remain errors. Voice is not enabled.

The original handoff is excluded from Ruff so historical files and hashes remain
unchanged. Its validator is run separately; `tools/check_repository.py` also checks
its manifest and scans publishable files for limited credential patterns/private
paths. This is not comprehensive secret detection or a production security audit.

## Database scaffold

The default database is `sqlite:///./var/girlframe.db`, relative to the current
directory. Run from the root. To isolate a local database:

```bash
export GIRLFRAME_DATABASE_URL=sqlite:////absolute/path/to/synthetic.db
python -m girlframe health
python -m alembic upgrade head
python -m alembic check
python -m alembic downgrade base
```

M0 only supports plain local SQLite URLs, without URI parameters. `.env.example`
documents the setting; `.env` is not auto-loaded. SQLite connections enable WAL,
foreign keys and a five-second busy timeout. This is a single-writer pilot design,
not multi-process coordination. Health may create the database and parent folder;
it never runs migrations. M0's historical empty scaffold is now extended by
revision `0001`: campaigns, membership, drafts, command inbox, audit events, setup
plans and resource mappings. Revision `0002` adds owned roles and the durable
character-role/nickname queue. Fresh/repeated upgrade, metadata check and downgrade
are tested against disposable synthetic databases.

Only delete disposable synthetic DBs to reset M0. Do not apply reset instructions
to campaign data. `downgrade base` now **drops application tables**; run it only on
disposable test databases. A local pre-upgrade SQLite backup was retained before
applying the additive migration. Full backup/restore automation and event replay
remain part of the unfinished broader M1 work before real gameplay data.

## Boundaries and next milestone

- `engine`: transport-independent typed identity and status projection; rules deferred.
- `engine_adapter`: read-only sandbox adapter; no subprocess or mutation methods.
- `_vendor/harpyframe`: reviewed minimal bridge, with source provenance documented.
- `discord_adapter`: private-response protocol and in-memory test fake.
- `services`: offline health and read-only engine status; no authorization or mutations.
- `database`: connection setup and empty metadata.
- `scenes`, `gm`, `handler`, `ai`, `delivery`: reserved namespaces only.

The current M1 phase implements trusted local read-only membership policy and real
Discord transport. Later M1 work adds database-backed campaigns, sheets, raw dice,
idempotency, event journal, outbox and crash/replay tests. Live testing requires
an authorized private test guild and securely provided bot credentials. Before
mutable rolls/finalization, resolve the legacy JSON/database authority boundary
and implement transactions, revisions, serialization and idempotency. The full
engine has been recovered and privately verified, but mechanics integration and
all official Plays are deferred. There is no claim of v1.3.11 implementation.

## Source and game rights

This is private development. No open-source license is granted for the new
application code by this repository; rights remain with their respective holders
pending an explicit licensing decision. GIRL FRAME is authored by Isabelle M.
Ruebsaat. The game, rulebook, official sheets, names and other third-party material
retain their own rights; this project does not relicense them or assert affiliation.
Third-party dependencies retain their respective licenses.

Do not commit official PDFs, real campaign saves, messages, credentials, or private
reference archives. Keep them outside the checkout. `.gitignore` is an aid, not
permission to commit sensitive content with `git add -f`.
