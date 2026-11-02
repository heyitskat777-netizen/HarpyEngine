# HarpyEngine development instructions

Read `README.md`, then the original handoff's `AGENTS.md` and active work order
under `GIRLFRAME_Discord_Codex_Handoff_v0.2/`. References to `planning/` in that
handoff mean this retained directory; do not duplicate or regenerate it.

Follow the handoff's authority, privacy, and engineering boundaries throughout
this repository. The owner accepted M0 and authorized **M1 read-only Discord bot**.
Implement only /help, /campaign_status and administrator /health with access checks.
The broader M1 ledgers/dice work is still deferred. Stop before engine writes or M2.

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
  `reports/M1_ACCEPTANCE.md`. Preserve M0's historical evidence. Keep offline,
  live login/registration and human slash-command outcomes distinct.
