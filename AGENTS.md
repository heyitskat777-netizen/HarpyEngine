# HarpyEngine development instructions

Read `README.md`, then the original handoff's `AGENTS.md` and active work order
under `GIRLFRAME_Discord_Codex_Handoff_v0.2/`. References to `planning/` in that
handoff mean this retained directory; do not duplicate or regenerate it.

Follow the handoff's authority, privacy, and engineering boundaries throughout
this repository. The current authorized implementation milestone is **M0 only**.
Stop after its acceptance report. M1 and later milestones need owner acceptance.

- Run `bash tools/install.sh`, then the checks in `README.md`.
- Use the existing checkout. Cloud tasks are isolated; create no worktree unless requested.
- Keep the original planning package unchanged, including its historical reports.
- Domain modules must not import Discord, AI SDKs, storage, or delivery adapters.
- No real campaign data, official PDFs, credentials, model calls, or live Discord
  connections belong in M0 source, fixtures, tests, logs, or CI.
- M0 now includes the explicitly authorized read-only v1.3.10 bridge integration.
  Keep full private engine archives, canonical state and secrets outside Git.
  Engine mutation/reconstruction is deferred; empty namespaces are intentional.
  Do not turn planning examples into implemented game mechanics.
- Record actual commands, output, counts, failures, and limitations in
  `reports/M0_ACCEPTANCE.md`. Do not claim live bot or rules readiness.
