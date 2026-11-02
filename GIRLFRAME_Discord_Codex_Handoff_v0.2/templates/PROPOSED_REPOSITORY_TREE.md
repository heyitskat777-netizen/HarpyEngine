# Proposed repository once Codex starts M0

```text
girlframe-discord/
├── AGENTS.md
├── README.md
├── .env.example
├── .gitignore
├── pyproject.toml
├── uv.lock                      # or other reproducible lockfile chosen in ADR
├── .github/workflows/ci.yml
├── alembic.ini
├── migrations/
├── planning/                   # this handoff, no licensed PDFs
├── src/girlframe/
│   ├── __main__.py
│   ├── config.py
│   ├── domain.py
│   ├── engine/{rules_registry,rolls,effects,permissions}.py
│   ├── services/{commands,queries}.py
│   ├── database/{models,repositories,unit_of_work}.py
│   ├── delivery/{outbox,discord_transport}.py
│   ├── discord_adapter/{bot,commands,views}.py
│   ├── scenes/coordinator.py
│   ├── ai/{model_gateway,context_builder,proposal_validator}.py
│   ├── gm/world.py
│   └── handler/agent.py
├── tests/{unit,integration,fake_discord,rules,golden,security}/
└── reports/M0_ACCEPTANCE.md
```

This is a **target**, not a claim that the bot exists. Codex may make minor layout changes with documented rationale but must respect the Engine/Discord/AI dependency boundaries.
