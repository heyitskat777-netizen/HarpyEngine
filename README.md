# HarpyEngine — GIRL FRAME read-only Discord bot

M0 is accepted. M1's first phase adds a real, guild-scoped read-only Discord bot
with `/help`, `/campaign_status`, and administrator `/health`. No rolls, engine
writes, AI, character actions or campaign creation are enabled. The broader M1
ledger/dice work is not complete.

Read `AGENTS.md` first when developing. The original planning handoff remains in
`GIRLFRAME_Discord_Codex_Handoff_v0.2/`; its `planning/` references refer to that
directory. The owner authorized the read-only M1 phase; stop before adding writes.

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
baseline; widen support only with validation. No tokens are required. The recovered
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
guild, then registers exactly three commands **in that guild only**. Sync replaces
this application's command set in that test guild; no global command sync occurs.
Gateway reconnects do not re-register commands. `Ctrl-C` and SIGTERM close the
client. Processes must be restarted after environment restoration/publication.

All replies are ephemeral with mentions disabled. Authorization runs server-side:

| Command | Access |
|---|---|
| `/help` | Authenticated members of the configured guild |
| `/campaign_status` | Explicit `status_user_ids`, or guild administrators if enabled, with audience approval |
| `/health` | Guild administrators only, and only when explicitly enabled by policy |

DMs, wrong guilds, and users without guild-member proof are denied before snapshot
access. Roles are derived from Discord's member permissions, never display names
or slash options. There are no player-supplied path/campaign selectors. SDK command
visibility is supplementary; changing Discord command permissions does not bypass
backend checks. Each command has a per-guild/user cooldown of 3 uses per 10 seconds.

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
printed to users. The bot does not post proactively in any channel.

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
it never runs migrations. Alembic has **zero revisions** in M0: `upgrade head`
only initializes its own version table; no campaign schema exists. Empty-scaffold
repeatability is tested, not future application migration correctness.

Only delete disposable synthetic DBs to reset M0. Do not apply reset instructions
to campaign data. M1 must provide reviewed migrations, backups and restore tests
before persistent campaigns are introduced. `downgrade base` presently has no
application revisions to reverse and leaves Alembic's empty version table.

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
