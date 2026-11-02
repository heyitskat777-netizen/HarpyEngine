# Milestone Development Master Plan | M0–M7

**Status:** proposed owner-approved-by-milestone plan. The handoff itself does not constitute an M0/M1 code completion or a passing rules audit. Implement and review **one milestone at a time**. Regression-testing chat is a separate verifier with read-only test artifacts.

## Global exit gate for EVERY milestone

- [ ] Source code is tracked and docs updated with exact changed files, module contracts and APIs.
- [ ] Runnable commands produce actual recorded output; no invented successful test claims.
- [ ] `ruff check`, formatting, schema/migration tests and milestone-specific `pytest` pass or documented blocking failures are fixed.
- [ ] No hardcoded tokens, private player messages, real campaign state, copyrighted PDFs or production API keys in repository or CI artifacts.
- [ ] All introduced state changes are campaign-scoped, authorized, versioned, replayable and audited.
- [ ] Crash/restart behavior works for the milestone's features; idempotency and outbox behavior verified.
- [ ] `reports/MX_ACCEPTANCE.md` includes passed/failed/skipped test counts and transcripts/command outputs.
- [ ] **STOP**. Owner/reviewer signs off before next milestone.

## M0: Repo and contract foundation

**Goal:** Reproducible local project with tested architecture and scripts, but **no fake complete RPG implementation**.

**Build:** `pyproject.toml`, pinned lock, typed package skeleton, `README`, `.env.example`, CI, `ruff`, `pytest`, SQLAlchemy/Alembic skeleton, mocked Discord adapter interface; install/health smoke; copied planning handoff; source/rules inventory and ADR decisions.

**Acceptance:** fresh checkout → setup → `pytest` → `ruff` → `python -m girlframe --help` works without Discord token or OpenAI key; contracts schema-check; no copyrighted PDFs or real snapshots; `M0_ACCEPTANCE.md` written.

**Exit limitations:** no campaign creation yet; fake-Discord adapter is not actual Discord connectivity.

## M1: Persistent campaigns, sheets, raw dice and event journal

**Goal:** AI-free runnable bot with one private guild; minimal draft character, roll ledger, public/private sheet, exactly-once game events and retryable delivery.

**Build:** migrations `guild_campaigns`, users/membership, `characters`, `events`, `rolls`, inbox dedupe, outbox. Typed service commands. Slash groups `/campaign create/join/status`, `/girl create`, `/sheet`, `/roll basic`, `/roll show`, `/ledger`, `/health`. Register user ownership, on-disk persistence, rebuild, CLI export/backup/restore, traceable result. One Girl per human account.

**Acceptance:** two-campaign isolation, duplicate interaction produces one roll and one event even over restart, stale update conflict, OS-generated faces, private sheet secret does not leak, fake Discord delivery failure retries without new roll, clean migration/replay. No AI calls.

**Exit limitations:** `/roll basic` is not a published Play, draft Girl is not a certified character builder.

## M2: Native `/play` wizard and selected official Plays

**Goal:** The primary mobile-friendly interactive Discord mechanics experience using the real printed rules for a small verified subset.

**Build:** persistent action/choice workflow, `PlayWizardView`, target/Heat/Asset legal dropdowns, “Confirm & Roll”, official options, `PendingPlayerChoiceView`, `/choice resume`, versioned rules registry, initial verified rules for Heat/Identity/Tag/Status and a limited Play set (e.g., Keep Your Head, Check Sensors, Engage). Expand to Disobey Orders and Flirt only after verifying other-player response and order contracts.

**Acceptance:** no illegal 6 Heat when only 4 available; 5+ mandatory spending; pre-roll Heat locked; post-roll Tag correct; 11+ and 7− exact published options for selected Plays; absent player freezes only affected action; duplicate click no reroll; mobile/select limits handled; published source page/test map per Play.

**Exit limitations:** no claim of complete GIRL FRAME coverage. Unknown Play returns `UNSUPPORTED_RULE` with source reference.

## M3: Rulebook engine, missions and recovery

**Goal:** Complete audited rule registry for the agreed version/house rules before claiming fully legal GIRL FRAME sessions.

**Build:** all Girl/Frame/Handler relevant Playbooks, Assets, Bonds, Status, NPCs/Harpies, Gorgons, combat, missions, Punishments, Requisitions, Off-Duty/Observation, all Low/High Strain dice/columns, cascades/endgames, Director prices, map movement rules.

**Acceptance:** every published Play registry item implemented OR explicitly reported unsupported; each has all result tiers/mandatory choices tested; RUL-001...RUL-010 from `RULES_PORT_PLAN.md` covered. Structural contract tests block incomplete followups and unearned Bond changes. A failed extraction never yields custody without later provenance.

**Exit limitations:** until complete coverage achieved, say `rules-subset`, NOT “officially complete”. If too large, split M3 into sub-PRs without skipping the gate.

## M4: Scene Coordinator and canon/knowledge ledgers

**Goal:** Multi-player asynchronous PBP without lost PC agency or Handler omniscience.

**Build:** scenes and participants, UTC+fictional timestamps, parallel-scene constraints, pending decisions, timed reminder jobs but no automatic fictional advancement, private-information grant events, scene-thread links, `/scene`, `/canon propose/review`, correction workflow, source-message provenance.

**Acceptance:** one PC cannot appear at incompatible locations, different scenes can progress separately, Handler cannot see secret disclosure until known, pending actions survive multi-day restart, message edits do not rewrite canon, facilitator correction leaves prior event and descendant flags; `/safety pause` halts impacted narrative posts.

## M5: AI GM

**Goal:** Fictional world, NPCs and GM rules guidance from schema-bound model outputs, validated before commit.

**Build:** model gateway (OpenAI Responses API), GM-only context builder, `AIProposal` schema, prompts/versions, citation/provenance, proposal validator, retry/escalation, NPC/Gorgon/Harpy goals, mission narrative, state-anchored narration, costs/limits, no model calls for basic commands.

**Acceptance:** canary secret cannot leak into NPC/player output; prompt injection does not mutate resources; trapped stale proposal rejected; escaped Harpy not narrated in custody; AI outage leaves pending action; uncertain rulings go to facilitator. Human evaluation required, not just unit tests.

## M6: AI Handler

**Goal:** A real in-fiction Handler with personality and constraints, separate from the objective GM.

**Build:** Handler sheet/Playbook, agenda, orders, duty/deadline triggers, personal & institutional goals, Handler-specific context view, Role-marked Discord output, Handler Plays/Punishments, separate prompt and proposal validation.

**Acceptance:** Handler cannot know unreported CHIFFON-like secret; direct order includes issuer/wording/scope; 7− Disobey prohibits voluntary defiance in fiction; handler does not impersonate player and its personal goals cannot bypass Engine; old/overdue Director prices resolve or explicitly breach with consequences.

## M7: Private multiplayer pilot and release review

**Goal:** 3–5 human players play an actual mission and recovery arc across days; state is consistent, confidential and recoverable.

**Build:** UX polish, system reliability and load testing, admin runbook, backups, campaign exports, privacy/retention, human observation, limited pilot retrospective. No public release without IP/content policy gate.

**Acceptance:** full offered mission → independent acceptance/decline → combat and roleplay → mission-end effects incl. Dog → Off-Duty and all mandatory Strain followups → canon ledger; moderator can audit every resource; 24–72h asynchronous restart/failure simulation; no forced PC dialogue; no secret leaks; satisfactory human narrative review. All rules coverage gaps disclosed.

## Dependencies

`M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7`

Some design research may occur earlier, but implementation must not bypass security or permission gates. AI role development can be prototyped with synthetic fixtures while rules and scene coordination are built, but cannot be promoted into real campaigns before M4/M5 gates.

## Ownership and test-chat coordination

Codex **implements**. Separate regtesting chat **reviews code/fixtures/logs and proposes tests**. Product owner **approves** milestone. Review chat must receive a fresh ZIP or Git commit diff plus `reports/MX_ACCEPTANCE.md`, not a textual statement that tests passed.
