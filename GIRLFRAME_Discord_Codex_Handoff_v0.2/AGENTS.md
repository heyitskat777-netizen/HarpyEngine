# Codex Repository Instructions | GIRL FRAME Discord Bot

You are implementing the separate GIRL FRAME **multiplayer Discord bot**, not continuing the existing The Long Winter game. Read `planning/README_START_HERE.md` and the active `planning/work_orders/CODEX_M*.md` before touching code.

## Authority and isolation

1. The published GIRL FRAME rulebook and official sheets are the rules authority. The GM Skill v1.3.9 is an **experimental reference** with known bugs. No copied code is assumed correct until tests compare it with the printed rules.
2. Human players exclusively choose voluntary Girl dialogue, Heat spending, player-facing options, intimacy, mission acceptance, secrets to reveal, and actions. AI cannot forge player consent. Fictional conditioning and compulsory consequences may restrict fictional options; OOC `/safety pause` always works.
3. The Engine is the only component authorized to commit mechanical/canon effects. AI GM/Handler produce validated proposals, not SQL updates. Discord callbacks pass typed commands to services, never mutate ORM models directly.
4. In-game Handler knowledge is strictly smaller than GM knowledge. No Handler-context prompt may contain unobserved GM-only or private PC secrets.
5. Discord posts, edits, deletes and AI narration are not themselves authoritative canon. Only committed, properly authorized game events are. Corrections are append-only superseding events.
6. Never reuse or import The Long Winter T194 campaign data, private users, the 100-turn stress-test states or real Discord messages as generic test fixtures. Synthetic examples only.
7. Do not claim production security, complete published rules, or AI autonomy merely because stub interfaces or format tests pass.

## Engineering discipline

- Begin with M0 and stop after the specified milestone. No speculative features or premature AI integration.
- Dependencies are pinned in a lockfile and periodically reviewed; pin a tested `discord.py` version, not a floating major. Do not hardcode credentials or send tokens, PDFs or private player content to logs or external services.
- Add typing, migration, pure-domain tests, integration tests with a fake Discord adapter and deterministic injected RNG **for tests only**. Production RNG must use an OS-backed source.
- Every mutation has campaign-scoped identity, a command idempotency key, distinct event indexes, expected version/revision, validated player authority, event provenance and a transactional outbox projection.
- Do not promise exactly-once Discord **delivery**; backend state is exactly-once under an idempotency key, Discord delivery is retryable and may require reconciliation to avoid duplicates.
- Avoid `MESSAGE_CONTENT` privileged intent and passive transcript ingestion in MVP. Respect consent/retention requirements before enabling passive monitoring.
- Use stable numeric Discord snowflake IDs as identifiers, not display names. Prefer non-ephemeral persistent action messages for multi-day interaction; private ephemeral components are not durable for a future day.
- Every milestone must write `reports/MX_ACCEPTANCE.md`, including executed commands, actual outputs, test count, failed/skipped checks, missing rules, known risks and unresolved decisions.
- If a required rule is unknown, STOP the resolution with `UNSUPPORTED_RULE`, document its rulebook location, and never make up a favorable consequence.
- No nondeterministic AI-dependent CI acceptance tests; use deterministic fake proposals and recorded fixtures. Human review is an extra gate for narrative quality.

## CI gates

`ruff check`, `ruff format --check`, unit/integration tests, migrations in a fresh DB, two-campaign isolation, idempotent roll/transaction replay, access-control and secret nonleakage checks, restart and outbox retry tests, package/contract schema checks, and test evidence. Later milestones add AI proposal schema tests, output grounding and human playtest gates.

## Deliverable

A running, independently deployable **private** Discord bot over sequential milestones, with source/test evidence and clear non-goals. Never start implementation of the next milestone without an explicit go-ahead from the project owner.
