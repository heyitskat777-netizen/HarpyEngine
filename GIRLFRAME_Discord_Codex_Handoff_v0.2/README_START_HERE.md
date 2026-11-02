# GIRL FRAME Discord GM Bot | Codex Handoff v0.2

**Product:** Private, asynchronous Discord tabletop game for 3–5 **human-controlled Girls**, with a separate AI GM, an in-fiction AI Handler, a deterministic GIRL FRAME rules engine, and a persistent Scene Coordinator.

**Status:** Planning artifacts and executable **package checks** only; NO Discord bot or game implementation is claimed. This handoff supersedes v0.1 for planning. **Not a rules-certified product.**

**Canon safeguard:** The existing The Long Winter campaign is **paused at Turn 194**, 2190-03-17 07:18. Neither HOLLOW/SAVERI nor any other historical campaign state is imported or changed. Every supplied sample is synthetic. Old 100-turn tests are NONCANONICAL.

## How to use with Codex

1. Create a **new private Git repository** for the bot. Do not commit game PDFs, real players' messages, Discord credentials, OpenAI API keys, or The Long Winter save.
2. Copy this handoff into the repository as `planning/` (you can delete `reference/` after extracting useful decisions). Set `AGENTS.md` at repo root.
3. Give Codex **`work_orders/CODEX_M0_START.md`** first. Each milestone must end with a test report, changed-file list, reproducible commands, and a *STOP* before the next milestone.
4. Upon M0 acceptance, give Codex `work_orders/CODEX_M1_ENGINE_LEDGER.md`; then proceed in order through M7.
5. Give the **separate regtesting chat** `verification/REGRESSION_CHAT_HANDOFF.md` and `verification/REGRESSION_CASES.json`. It should review evidence independently and never write to the actual campaign.
6. Run `python verification/verify_handoff.py` against this folder to verify the planning package, JSON schemas, sample fixtures, references, and cross-links. This does **not** test a running bot.

## Document map

| Read order | File | Purpose |
|---|---|---|
| 1 | `AGENTS.md` | Unambiguous coding guardrails, source and authority hierarchy |
| 2 | `docs/PRODUCT_AND_SCOPE.md` | Product behavior, defaults, exclusions, desired player experience |
| 3 | `docs/ARCHITECTURE.md` | Engine / GM / Handler / Coordinator / Discord boundaries |
| 4 | `docs/STORAGE_EVENT_MODEL.md` | Database tables, event transactions, roll receipts, projections |
| 5 | `docs/DISCORD_UX.md` | Slash commands, `/play` interactive wizard, pending choices, UI limitations |
| 6 | `docs/RULES_PORT_PLAN.md` | Published-rule matrix, page references, v1.3.9 defects, certification policy |
| 7 | `docs/AI_GM_HANDLER.md` | Separate agent contexts, structured proposals, hallucination defenses |
| 8 | `docs/SECURITY_OPS.md` | Ownership, secrets, concurrency, retention, safeguards, outages |
| 9 | `docs/MILESTONE_MASTER_PLAN.md` | M0–M7 goals, exclusions, dependencies, release gates |
| 10 | `docs/DECISIONS_RISKS.md` | ADRs, decisions needing owner input, failure modes |
| 11 | `contracts/*.schema.json` | Versioned illustrative API/data contracts; schemas not DB migrations |
| 12 | `fixtures/*`, `verification/*` | All-synthetic example records and a regression-chat test matrix |
| 13 | `work_orders/*` | Standalone Codex task prompts and review template |

## Fixed decisions vs provisional recommendations

**Fixed:** Human PC authority; real dice; exact published mechanics where implemented; only Engine commits; private information filtered before AI; pending choices survive restart; state/canon from DB, not Discord messages; no silent fictional-time advancement; mandatory safety pause; experimental campaign data isolated.

**Provisional:** Python 3.12+, `discord.py`, SQLAlchemy + Alembic, SQLite WAL with one writer for private pilot, PostgreSQL when scaling; one campaign per Discord guild at MVP; explicit slash interactions instead of passive RP scanning; OpenAI Responses API in later milestones; private pilot only. These defaults can be revised through documented ADRs.

## Definition of done

A milestone is not done when code simply runs. It is done only when its acceptance cases pass **against clean, synthetic fixtures**, its security checks pass, the report cites commands and outputs, there is a documented rollback/migration path, and the user approves moving to the next milestone.

## Source and platform notes

- GIRL FRAME was authored by Isabelle M. Ruebsaat. Consult the separately supplied official rulebook and official sheets as the **published** rules authority. Do not redistribute copyrighted text or images in an open-source repository without permission. The sample code and fixtures in this package contain no licensed book text beyond rule names and tiny factual references.
- v1.3.9 is the experimental **GM Skill** version, not the published game edition. The known 100-turn regression failures remain unresolved and must become tests, not be inherited unquestioned.
- The previously created HTML UI prototype and PNG screenshots are separate **nonfunctional visual references**. They are not included as real Discord components or promised capability.
- Official platform reference URLs and verification date are in `docs/PLATFORM_SOURCES.md`.
