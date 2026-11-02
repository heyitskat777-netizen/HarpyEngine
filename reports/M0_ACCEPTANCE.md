# M0 acceptance report

**Status: PASS for local M0 foundation checks; pending owner/reviewer acceptance.**
**Date:** 2026-11-02. **Scope:** foundation only; stop before M1.

## Read-only integration update (current)

The owner supplied and verified the corrected private v1.3.10 package after the
initial foundation, then authorized a read-only integration. Added an explicitly
configured sandbox adapter, service/source protocol, immutable status projection,
local `engine-status` CLI and reviewed vendored bridge. No Discord endpoint or
engine mutation was added. Original foundation evidence is retained below.

Current command transcripts: [M0_ENGINE_VALIDATION.txt](M0_ENGINE_VALIDATION.txt).

| Current check | Actual outcome |
|---|---|
| Application tests | **51 passed, 0 failed, 0 skipped, 0 xfailed** (30 original + 21 new) |
| Ruff lint / format | All checks passed; 37 Python files formatted |
| Strict mypy | No issues in 25 source files |
| Locked offline sync | No dependency changes; lock remains valid |
| Planning validator / manifest | Passed; 40 original manifest entries preserved |
| Integration privacy | Only turn/paused returned; strict types, malformed/missing/oversized state rejected; private canaries absent |
| Isolation | Missing marker and symlinked roots/state rejected; no DB created by status; synthetic source bytes unchanged |
| Private runtime smoke | Configured disposable runtime read succeeded; runtime and canonical template hashes unchanged |
| Build | Offline wheel/source distribution succeeded; reviewed bridge/adapter included |
| Artifact inspection | 29 wheel entries and 92 source-distribution entries; no PDFs, campaign JSON, DBs, private archive, cache or virtualenv |
| Installed-wheel smoke | New wheel installed in separate environment; engine-status worked from outside source with synthetic data |
| Remote CI | Workflow unchanged; current remote outcome not yet observed |

The private engine intake's **66 focused tests** and zero-error/zero-warning
validation are separate, earlier results; they are not counted in the 51 tests.
No real campaign values are recorded in these public/publishable evidence files.
Full private smoke output and runtime/template hashes remain outside Git.
Source provenance and integration instructions are in
[ENGINE_SOURCE_INVENTORY.md](../docs/ENGINE_SOURCE_INVENTORY.md).

Only the minimal bridge was incorporated into Git. Full private engine code/data
remain external references. The integration requires no private archive for CI;
an operator supplies a disposable runtime for local status use. A marker is an
accident-prevention measure, not authentication or a guarantee of atomic reads.
Audience approval and per-user/guild/campaign authorization are required before
Discord exposure. Resolve JSON/database authority and implement transactional
writes, revisions and idempotency before enabling any engine mutation in M1.

Changed since the initial baseline: `.env.example`, `AGENTS.md`, `README.md`,
`docs/M0_ARCHITECTURE_DECISIONS.md`, `src/girlframe/config.py`,
`src/girlframe/__main__.py`, `tests/test_foundation.py`, and this report.
New: `docs/ENGINE_SOURCE_INVENTORY.md`, `reports/M0_ENGINE_VALIDATION.txt`,
`src/girlframe/_vendor/` (3 files), `src/girlframe/engine/status.py`,
`src/girlframe/engine_adapter/` (2 files), `src/girlframe/services/engine_status.py`,
and `tests/test_engine_status.py`. No dependencies or original handoff files changed.

## Initial foundation outcome

Installable typed package with all requested namespaces, a strictly validated
identity/context contract, fake private-response transport, offline health service
and CLI, local SQLite connection configuration, empty Alembic scaffold, pinned
runtime/dev dependencies and uv lock, installation script, documentation, CI and
synthetic offline tests. The original handoff is unchanged.

No campaign tables, Discord commands, real Discord transport, authorization implementation,
roll engine, game mechanics, AI calls, or campaign import is implemented. Empty
namespaces are intentional. Engine recovery was not required for the initial foundation.

## Initial foundation checks (historical)

Full final command output and exit codes: [M0_VALIDATION.txt](M0_VALIDATION.txt).

| Check | Actual outcome |
|---|---|
| Python / uv | 3.12.14 / 0.12.23 |
| Initial dependency resolution/install | 36 resolved packages including project; 35 installed distributions |
| `bash tools/install.sh` | Locked setup succeeded; repeat run checked 35 packages without changes |
| Locked offline sync | Exit 0; 35 packages checked |
| Ruff lint | All checks passed |
| Ruff format check | 27 Python files already formatted |
| Strict mypy | No issues in 18 application source files |
| `pytest -q --junitxml=var/pytest.xml` | **30 passed, 0 failed, 0 skipped, 0 xfailed** |
| CLI `--help` | Exit 0, help text shown without secrets |
| CLI `health` | Exit 0, local SQLite checked; Discord/rules flags false |
| CLI `start` | Expected exit 2; explicitly reports no Discord runtime |
| Alembic `upgrade head` / `check` | Exit 0; no new upgrade operations detected |
| Temporary migration test | Upgrade repeated twice, check and downgrade base succeeded; only empty Alembic version table exists |
| SQLite behavior | WAL, foreign keys and busy timeout verified; invalid FK insert rejected |
| Planning package validator | PASS: 34 required files, 4 schemas and 4 fixtures |
| Original manifest | 40/40 sizes and SHA-256 hashes matched |
| Fresh source copy install | New virtual environment under `/tmp`; `uv sync --locked --all-groups --offline` succeeded using verified cache; help, health and 30 tests passed |
| Build | Offline wheel and source distribution built successfully |
| Distribution inspection | Wheel: 22 entries, including `py.typed`; source distribution: 81 entries; neither contained PDFs, DBs, cache or virtualenv |
| Wheel install | Replaced editable install in fresh environment; CLI launched successfully from `/tmp` outside source |
| discord.py compatibility smoke | 2.7.1 imported; package metadata requires Python >=3.8; empty intents have message-content disabled; no gateway constructed |
| GitHub Actions | Workflow added; remote CI outcome not yet observed |

The separate historical **86 planned cases remain NOT_RUN**; do not count them as
executed tests. Statement/branch coverage percentage is **not measured**. Local
network blocking applies to in-process tests. No live API tests executed.

## Dependency versions

Runtime: discord.py 2.7.1, SQLAlchemy 2.0.55, Alembic 1.20.1, Pydantic 2.14.2.
Development: jsonschema 4.26.0, pytest 9.2.0, Ruff 0.17.3, mypy 1.20.2.
Build backend: Hatchling 1.33.0. All direct requirements are exact pins; uv.lock
records the resolved runtime/development dependency graph and artifact hashes.

## Diagnosis and corrections during implementation

- Default uv home cache was read-only. Installation now uses `.cache/uv`, ignored
  by Git. Sandbox network initially failed; dependency installation succeeded
  through supported escalation with inherited proxy/TLS verification intact.
- Initial Ruff checks found line wrapping/formatting issues in new files. Applied
  Ruff formatting; final checks pass. The first and final executable test suites
  both passed; no failed/skipped application test is concealed.
- Official documentation lookup at
  `https://discordpy.readthedocs.io/en/stable/intro.html` returned HTTP 403 through
  the configured route. No live Discord documentation/API compliance claim is
  made. Installed official package metadata and an offline import were verified.
  Real interaction behavior must be checked against current official docs in M1.
- Cross-filesystem fresh install fell back from hardlinks to copying; installation
  succeeded. Build warned that the cache was under the source root; actual wheel
  and source distribution inspection confirmed cache/private data were excluded.

## ADR deviations and limits

See [M0_ARCHITECTURE_DECISIONS.md](../docs/M0_ARCHITECTURE_DECISIONS.md).
The tested Python baseline is deliberately restricted to 3.12 rather than claiming
all later Python versions work. Retain the original handoff directory instead of
renaming/copying it into `planning/`. Root README/AGENTS map the old paths.

Ruff excludes the original historical package; strict typing covers new application
source. Its historical validator has known limited credential scanning; the new
additive checker scans publishable files including Python and verifies manifest
hashes. Pattern scans do not establish absence of every possible credential.
Illustrative roll/AI schemas are not domain enforcement implementations.

SQLite is one-writer local pilot infrastructure. No application migration or
persistent campaign behavior has been verified. Future commands must authenticate
and authorize server-side; a typed principal is not proof of membership. The fake
transport does not prove Discord privacy, acknowledgement timing or retry behavior.

Game mechanics, RNG, two-campaign isolation, idempotent rolls, actual outbox/restart
recovery, rules audit and GM/Handler knowledge filtering belong to later milestones.
No real PDFs, private references, old campaign state or credentials are introduced
into Git. No environment draft updates or publication were performed.

## M1 prerequisites

Owner/reviewer acceptance of M0; start M1 with authorized read-only commands and synthetic data.
Before live tests, provide an authorized private guild/application and bot credentials
through secure configuration. Confirm deployment privacy and backup/retention plans
before using real campaign data. Decide public source licensing separately.
Engine mechanics integration and official rule implementations remain deferred.

## Initial foundation files

All entries below are new. No original handoff file was changed.

- `.env.example`
- `.github/workflows/ci.yml`
- `.gitignore`
- `.python-version`
- `AGENTS.md`
- `README.md`
- `alembic.ini`
- `docs/M0_ARCHITECTURE_DECISIONS.md`
- `migrations/env.py`
- `migrations/script.py.mako`
- `migrations/versions/.gitkeep`
- `pyproject.toml`
- `reports/M0_ACCEPTANCE.md`
- `reports/M0_VALIDATION.txt`
- `src/girlframe/__init__.py`
- `src/girlframe/__main__.py`
- `src/girlframe/ai/__init__.py`
- `src/girlframe/config.py`
- `src/girlframe/database/__init__.py`
- `src/girlframe/database/base.py`
- `src/girlframe/database/connection.py`
- `src/girlframe/delivery/__init__.py`
- `src/girlframe/discord_adapter/__init__.py`
- `src/girlframe/discord_adapter/fake.py`
- `src/girlframe/discord_adapter/transport.py`
- `src/girlframe/engine/__init__.py`
- `src/girlframe/engine/identity.py`
- `src/girlframe/gm/__init__.py`
- `src/girlframe/handler/__init__.py`
- `src/girlframe/py.typed`
- `src/girlframe/scenes/__init__.py`
- `src/girlframe/services/__init__.py`
- `src/girlframe/services/health.py`
- `tests/conftest.py`
- `tests/test_database.py`
- `tests/test_foundation.py`
- `tests/test_repository_check.py`
- `tools/check_repository.py`
- `tools/install.sh`
- `uv.lock`
