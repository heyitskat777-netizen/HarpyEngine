# Requirement → Regression Traceability

| High-impact requirement | Regression case IDs | Implementation gate |
|---|---|---|
| Player ownership / human agency | M1-013, M2-007, M2-013, M5-004, M6-003, M7-004 | Each affected milestone |
| Multi-campaign isolation and private sheets | M1-004, M1-005, M1-016, M4-003 | M1 + M4 |
| Exactly-once DB roll/commit vs retryable Discord sends | M1-006...M1-012, M2-006 | M1 + M2 |
| Event journal cannot be rewritten via message edit | M1-014, M4-006, M7-005 | M1 + M4 + M7 |
| Pre-roll Heat and post-roll Tag legality | M2-002...M2-005 | M2 |
| Real secondary target response | M2-007, M2-008, M2-013, M2-015 | M2 |
| Status exchange / Oldgen maxim | M3-001 | M3 |
| Off-Duty 7− and Princess Show Dog | M3-002, M3-003 | M3 |
| Dog punishment at mission end | M3-004, M7-001 | M3 + M7 |
| Strain cascades and escape escalation | M3-005, M3-006, M3-013, M7-002 | M3 + M7 |
| Flirt 11+ printed choices | M2-009, M3-008 | M2/M3 |
| Director price due | M3-009, M6-005 | M3 + M6 |
| Harpy refusal and consent separation | M3-010, M5-003 | M3 + M5 |
| Concurrent scenes and fictional chronology | M4-001, M4-002, M4-008, M4-009 | M4 |
| GM facts separated from Handler knowledge | M4-004, M6-001, M6-007 | M4 + M6 |
| Prompt injection and model result constraints | M5-001...M5-006 | M5 |
| Safety pause outside fiction | M1-020, M4-007, M7-006 | M1 + M4 + M7 |
| Complete mission pilot / recover from restart | M7-001...M7-008 | M7 |

**Legend:** `REGRESSION_CASES.json` currently lists **planned**, not executed, tests. No pass/fail state should be changed without a real repository commit and reproducible test evidence. A requirement can be partially tested in an earlier milestone and still remain unverified for full rules fidelity.
