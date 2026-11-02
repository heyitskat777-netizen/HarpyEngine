# CODEX WORK ORDER M0 | Foundation and Reproducible Environment

**Task:** Create the *initial repository infrastructure only*. Read `planning/AGENTS.md`, `planning/docs/PRODUCT_AND_SCOPE.md`, `planning/docs/ARCHITECTURE.md`, `planning/docs/MILESTONE_MASTER_PLAN.md`, and `planning/docs/DECISIONS_RISKS.md`. The planning directory is a contract, **not source code to execute**. This is a fresh repo, not the live GIRL FRAME campaign.

## Deliverables

1. Python 3.12+ application package under `src/girlframe/` with separate namespaces `discord_adapter/`, `engine/`, `services/`, `database/`, `scenes/`, `gm/`, `handler/`, `ai/`, `delivery/`. Empty or genuinely useful typed interfaces are okay; no faked completed implementations.
2. `pyproject.toml` and reproducible dependency lock containing `discord.py`, SQLAlchemy 2.x, Alembic, Pydantic v2, pytest, ruff, chosen formatter/type checker. Pin tested versions and record Python version.
3. `.gitignore`, `.env.example` with placeholders only, `README.md` with exact setup/run/test commands, public source/license statement that does NOT relicense GIRL FRAME.
4. Alembic scaffold and a documented database configuration strategy. Migration tables themselves belong to M1.
5. Fake Discord transport interface and typed request principal shape for offline tests; CLI with `python -m girlframe --help`, health/no-token startup stub.
6. CI workflow running `ruff check`, `ruff format --check`, `pytest`, source formatting/type gate if configured, and package contract checker.
7. `docs/M0_ARCHITECTURE_DECISIONS.md` and `reports/M0_ACCEPTANCE.md` with actual executed test output.

## Explicit non-goals

No live Discord bot token, no AI calls, no official GIRL FRAME Play implementation, no campaign import, no persistent GUI, no roleplay dialogue, no invented PDF-derived rules.

## Acceptance evidence

- Fresh setup `python -m pip install ...` or agreed lockfile command works.
- `python -m girlframe --help` works without secrets.
- `ruff check .`, `ruff format --check .`, `pytest -q` pass or report exact failures.
- Automated tests run offline using fake transport only; no external network calls.
- `rg`/secret scan excludes `.env`, raw official PDFs, campaign data and Discord tokens.
- Top-level types/interfaces do not import `discord.py` from `engine` modules.
- Document any platform mismatch discovered via current official docs.

## Final report format

```
M0 status: PASS / BLOCKED
Changed files: ...
Commands executed and output: ...
Tests: pass / fail / skip, coverage as measured
Risks / ADR deviations: ...
Next milestone prerequisites: ...
```

**STOP after M0. Do not start M1 without explicit owner acceptance.**
