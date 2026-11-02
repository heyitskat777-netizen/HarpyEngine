# HarpyEngine — GIRL FRAME Discord foundation

M0 provides an installable Python package, an offline health CLI, typed identity
and fake transport interfaces, and an empty SQLAlchemy/Alembic scaffold. It does
not connect to Discord, run AI, implement game rules, or create campaigns.

Read `AGENTS.md` first when developing. The original planning handoff remains in
`GIRLFRAME_Discord_Codex_Handoff_v0.2/`; its `planning/` references refer to that
directory. M0 is the active work order. Stop before M1 until owner acceptance.

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
baseline; widen support only with validation. No tokens are required. The old
engine's `tools/bootstrap_dev.py` and `tools/verify_engine.py` are not available.

`health` executes a local SQL query and reports `discord_connected: false` and
`rules_implemented: false`. `start` deliberately exits **2**, explaining that no
Discord runtime exists yet. Health success is not bot/game readiness.

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
or model integration is tested. The historical 86-case catalog remains NOT_RUN;
it is not the executable M0 suite. Coverage percentage is not currently measured.

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

- `engine`: transport-independent typed identity; rules deferred.
- `discord_adapter`: private-response protocol and in-memory test fake.
- `services`: offline foundation health only; no authorization or mutations.
- `database`: connection setup and empty metadata.
- `scenes`, `gm`, `handler`, `ai`, `delivery`: reserved namespaces only.

M1 adds server-side membership/authorization, campaigns and sheets, raw dice,
idempotency, event journal, outbox, real Discord transport, and persistence/restart
tests. Live testing will require an authorized private test guild and securely
provided bot credentials. Engine recovery/reconstruction and all official Plays
are deferred. There is no claim of v1.3.11 Scene Integrity Engine support.

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
