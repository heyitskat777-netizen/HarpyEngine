# M1 read-only Discord phase acceptance

**Status: PASS for the authorized read-only phase. Full original M1 is incomplete.**
**Date:** 2026-11-02. **Branch:** `codex/m1-read-only`, based on accepted M0.

## Result

Actual `discord.py` Gateway bot with three guild-scoped commands: `/help`,
`/campaign_status`, and administrator `/health`. All replies are ephemeral and
mentions are disabled. Authorization rejects wrong guilds, DMs and nonmember
identities before snapshot access; campaign status requires explicit membership
or enabled administrator access plus audience approval. Health requires enabled
administrator access. Policies are stored locally and survive process restarts.

Startup verifies authenticated application identity and guild access before
synchronizing exactly three test-guild commands. No global commands are registered.
SDK cooldowns limit each command to three calls per user/guild per ten seconds.
Filesystem work is deferred to worker threads after private acknowledgement.
SIGINT/context cleanup and SIGTERM close the client. Inherited proxy routing and
TLS verification are preserved. No token is stored in code, policy or evidence.

A synthetic status-only fixture (turn zero, paused) is used for the live test.
No private campaign data is sent to Discord. This fixture is not a runnable game
engine. The original private engine template remains unchanged (120/120 file
hashes match intake). No game mutations, rolls, AI or player actions are enabled.

## Validation evidence

Commands and sanitized results: [M1_VALIDATION.txt](M1_VALIDATION.txt).
Design and authorization boundary: [M1_READ_ONLY_DESIGN.md](../docs/M1_READ_ONLY_DESIGN.md).

| Check | Outcome |
|---|---|
| Offline executable suite | **74 passed; 0 failed, 0 skipped, 0 xfailed** |
| Ruff lint | All checks passed |
| Ruff format | 43 Python files formatted |
| Strict mypy | No issues in 29 application source files |
| Locked offline installation | Succeeded; existing dependency versions unchanged |
| `start --config ... --check` | Exit 0; validates policy/source offline without a token |
| Planning validator | PASS: 34 required files, 4 schemas, 4 synthetic fixtures |
| Original handoff manifest | 40/40 sizes/hashes preserved |
| Publishable-file scan | No findings; limited pattern scan, not full security certification |
| Build and artifact inspection | Wheel/source distribution passed; 33/102 entries; no private data, token, DB, campaign JSON, var/cache/venv paths |
| Secure runtime binding | Owner-applied direct `DiscordBot` variable reported ready; value never printed |
| Discord REST identity | Token authentication and configured application match succeeded |
| Initial guild lookup | Failed HTTP 404 / Discord 10004; owner corrected installation |
| Gateway | READY observed after corrected installation |
| Command registry read-back | Exactly campaign_status, health, help in the test guild; zero global commands |
| Human slash-command smoke | Owner confirmed all three worked with private replies |
| Private engine integrity | 120/120 original template files unchanged |
| Remote CI | Workflow updated; remote run outcome not yet observed |

The bot is running in the current development session. Processes do not survive
publication/restoration and are not production hosting. Restart via
`bash tools/run_discord_dev.sh` with the secure token available and existing local
policy retained. No environment configuration was published by this work.

## Diagnosed failures and limits

- Token was initially absent; after the owner applied the draft, direct secure
  delivery became ready. No duplicate token requirement or token disclosure was
  requested. Application public key is not used by this Gateway implementation.
- Initial live startup stopped before sync on Unknown Guild. After the owner fixed
  installation, registration, Gateway readiness and human commands succeeded.
- Managed command sandbox blocked asyncio worker-thread socketpair wakeups. An
  interrupted test run completed 50 tests before hanging. Running offline pytest
  with supported escalation resolved the executor constraint; the test fixture
  continued to forbid outbound network operations.
- Python 3.12's known discord.py import of deprecated `audioop` initially interrupted
  collection. Only that exact deprecation is filtered; other warnings remain errors.
  Voice and privileged intents are not enabled.
- A new cooldown test initially lacked a real timestamp on the fake interaction.
  Corrected it with a deterministic timestamp; final 74-test run passes.
- Discord's developer site returned HTTP 403. Official discord.py quickstart source
  at `https://raw.githubusercontent.com/Rapptz/discord.py/v2.7.1/docs/quickstart.rst`
  was readable (HTTP 200); installed SDK source/types were inspected. Live Gateway,
  registration and private response behavior were separately verified.

Coverage percentage is not measured. Live denial with a second human account,
forced reconnect/failure injection, and long-duration hosting are not verified.
Offline permission tests cover allowed/denied users, admin flags, audience approval,
wrong guilds and DMs. SDK permission visibility is not the authority boundary.

## Not completed: broader original M1

The original M1 campaign/character/dice/ledger work order is intentionally not
implemented in this read-only phase. M1-001 through M1-012 persistence, replay and
outbox acceptance cases are **UNRUN**, not counted in these 74 tests. The historical
86-case catalog and private engine's earlier 66 focused tests remain distinct.

Next phase requires reviewed database schema/migrations, database membership and
campaign administration, characters/sheets, immutable OS-backed raw dice receipts,
command idempotency, revision checks, transactional event journal, durable outbox,
backup/restore and crash/replay tests. Settle one authoritative database/event
service before adapting mutable engine behavior; the legacy multi-file finalizer
must not be called directly from callbacks. No M2 Plays or AI are implemented.

## Changed files

The original planning package and private engine are unchanged.

- `.env.example`
- `.github/workflows/ci.yml`
- `AGENTS.md`
- `README.md`
- `config/discord-policy.example.json`
- `docs/M1_READ_ONLY_DESIGN.md`
- `pyproject.toml`
- `reports/M1_ACCEPTANCE.md`
- `reports/M1_VALIDATION.txt`
- `src/girlframe/__init__.py`
- `src/girlframe/__main__.py`
- `src/girlframe/discord_adapter/__init__.py`
- `src/girlframe/discord_adapter/bot.py`
- `src/girlframe/discord_adapter/config.py`
- `src/girlframe/discord_adapter/runtime.py`
- `src/girlframe/services/read_only_bot.py`
- `tests/test_foundation.py`
- `tests/test_read_only_bot.py`
- `tools/run_discord_dev.sh`
- `tools/setup_discord_dev.py`
