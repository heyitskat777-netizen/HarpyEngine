# HarpyEngine development instructions

Read `README.md`, then the original handoff's `AGENTS.md` and active work order
under `GIRLFRAME_Discord_Codex_Handoff_v0.2/`. References to `planning/` in that
handoff mean this retained directory; do not duplicate or regenerate it.

Follow the handoff's authority, privacy, and engineering boundaries throughout
this repository. M0 is accepted. The owner authorized **M1 server setup and saved
character onboarding** after the read-only phase. Read `docs/PROJECT_ROADMAP.md`
and the additive work orders under `docs/work_orders/`. Build resumable setup,
membership, dropdown draft sheets, and owner-confirmed cosmetic role/nickname sync.
The owner explicitly authorized these Discord tags and continuation of the remaining
M1 dice/ledger, safety, durable delivery and local backup/rebuild foundation.
The owner subsequently authorized continuation into M2 and confirmed that JANUS-B
uses official JANUS rules while keeping its Discord label. M2A starting choices are implemented and verified. The owner requested further
continuation; M2B and M2C are implemented. Handler/NPC setup is implemented; the owner authorized further M2 continuation. The current owner instruction explicitly authorizes beginning M3 development.
Read `docs/work_orders/M3_RULES_COMPLETION.md` and the original `CODEX_M3_RULES.md`.
M3 is now scoped into M3A–M3H; begin with the source inventory and M2 interaction audit.
M2 implementation/deployment is complete, but independent rules review and human
play-testing remain pending. Do not fabricate certification or remove a release gate.
Keep the frozen running bot available while developing; stop after M3 for review.
AI and M4 remain outside the authorized milestone.
The owner now delegates future ambiguous-rule decisions to Codex's reasoned
recommendations. Apply them without repeatedly asking, preserve earlier explicit
owner choices, and record source/rationale/adjustment notes in
`docs/CAMPAIGN_RULINGS.md` and `rules/registry.json`. Mark delegated interpretations
as requiring printed-rule clarity review. This does not grant player consent,
independent certification, milestone sign-off or permission to publish the
environment or deploy M3 gameplay. Sanitized source pushes remain authorized.
Missing implementations still fail closed; do not disguise them as rulings.
Recovered-engine writes and AI remain deferred. Record partial scope honestly.

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
  `reports/M3_ACCEPTANCE.md` for M3 work. Preserve M0/M1 historical evidence. Keep offline,
  live login/registration and human slash-command outcomes distinct.
