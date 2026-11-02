# CODEX WORK ORDER M2 | Native Play Wizard and Verified Core Rules Subset

**Prerequisite:** M1 accepted, full tests green. Read `planning/docs/DISCORD_UX.md`, `RULES_PORT_PLAN.md`, `STORAGE_EVENT_MODEL.md` and the official PDF before implementing a Play.

**Build:** `/play` private menu, legal Play/target/Heat/Asset selectors, pending action table, pre-roll lock, immutable roll receipt, post-roll option selection, `/choice resume`, persistent other-player prompts, source-linked event completion. Implement Heat/Identities/Tags/Status mechanics and a small audited official Play subset (prioritize Keep Your Head, Check Sensors, Engage). Add Disobey Orders and Flirt only after the target-response workflow works and full published tier options are verified.

**Acceptance:** `M2-*` test cases in regression matrix, three-tier exact option counts for each implemented Play, two-user pending choices, 5+ Heat mandatory spend, no late Heat edits, no reroll on duplicate click, correct 11+ selections, mobile UX, permissions and restart. Rules registry records source page and test IDs. Unimplemented Play results in `UNSUPPORTED_RULE` rather than improvized fiction.

**Explicit stop:** Never claim official rule completeness. Do not initiate AI or M3 work. Write `reports/M2_ACCEPTANCE.md` and STOP.
