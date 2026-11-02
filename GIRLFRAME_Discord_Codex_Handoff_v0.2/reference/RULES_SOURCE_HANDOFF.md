# Source Handoff: v1.3.9 Candidate and 100-Turn Findings

**Published rules:** `GIRL_FRAME_rulebook.pdf` and `GIRL_FRAME_official_sheets.pdf` supplied by the user (private reference material; not included in this package). Copyright belongs to original publisher/creators; separate rights/permission review required before public redistribution.

**Existing prototype:** `GIRL_FRAME_SINGLE_PROJECT_SOURCE_v1.3.9_T194_CANDIDATE.md` (approximately 0.6 MB) contains embedded source of an *experimental single-player ChatGPT GM Skill* and a paused *real* campaign. **DO NOT load or migrate its `state/campaign.json`, NPC relationships or game history into a default multiplayer bot.** Its reusable code sections `scripts/gm.py`, `scripts/enforcement.py`, `scripts/operations.py`, `scripts/director.py`, `scripts/map_engine.py`, `scripts/canon.py` may be consulted privately for architecture and then independently rewritten or extracted only after review.

**Observed tests:** v1.3.9's 100-turn isolated sandbox finalized 100 turns with 0 validator errors / 1 warning, yet violated printed rules and generated internally contradictory prose. This is direct evidence that “engine validates” is **not** sufficient. Critical defects: mandatory High Budget6 second-column cascade unexecuted; Harpy escaped in structured state but later narrated at base. Additional defects: Low Rebellion prisoner escape missing escalation, misapplied Flirt 11+ result, harsh Off-Duty and Princess choices omitted, overdue Director price unacted, generic reciprocal dialogue. See `docs/RULES_PORT_PLAN.md`.

**Provenance rule:** A previously successful test of an old candidate is evidence for that narrow invariant only. The new Discord bot must not claim all printed mechanics are verified until full registry and independent regression passes. Keep The Long Winter canonical T194 paused and totally separate from synthetic fixtures.

**Reference UX:** `GIRLFRAME_Discord_UI_Mockup_Pack.zip` from earlier chat is an *offline HTML demo*, not a Discord bot. `reference/UI_MOCKUP_DESIGN_NOTES.md` maps its seven flows to real components. Use the images as inspiration only.
