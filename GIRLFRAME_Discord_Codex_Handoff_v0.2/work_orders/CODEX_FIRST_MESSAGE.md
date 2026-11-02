# One-message Codex kickoff (copy into Codex after attaching the handoff)

You are starting development of a private, asynchronous multiplayer GIRL FRAME Discord GM bot. The full planning handoff is in `planning/GIRLFRAME_Discord_Codex_Handoff_v0.2/` (or at repository `planning/` if extracted directly). Start with `README_START_HERE.md` and `AGENTS.md`, then read `docs/MILESTONE_MASTER_PLAN.md` and `work_orders/CODEX_M0_START.md`.

Implement **M0 ONLY**: Python package skeleton, tested dependency lock, CI, migration scaffold, fake Discord adapter, offline tests, CLI smoke, README and honest acceptance report. The engine has deterministic rules authority; real players control their Girls; AI GM and Handler will only be added in later milestones. Do not import The Long Winter campaign or any user PDF into a public repo. Use no Discord token or OpenAI key during M0. Respect all milestone guards and source priority. Use the planning JSON schemas and synthetic fixtures as cross-component contracts; preserve no private user data.

After implementation, run the actual tests and produce `reports/M0_ACCEPTANCE.md` with commands, outputs, file list, known limits and a clear `PASS` or `BLOCKED`. **Stop before M1 and await owner approval.**
