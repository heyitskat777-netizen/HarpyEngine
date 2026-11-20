# Narrative death limit verification

Verified from campaign-opening base
`b146b1399d324b1a403753744214bbaa2e0352b3`. The package manifest records
the exact follow-on revision. [Narrative rules](../docs/work_orders/CAMPAIGN_OPENING.md)

| Scope | Executed result |
|---|---|
| Feature and affected regression suite | 104 passed in 74.96 seconds |
| Configured CI selection | 49 tests collected |
| Changed Python | Ruff lint and format passed for six files. Scoped mypy passed for five source files. |
| Repository safeguard | Repository scan reported zero findings. |

The Narrative tests exercise a real low Defeat result. The existing decision
remains pending after a death choice without confirmation, preserving both
the original character and dice receipt. A separate case confirms the first
death through the native Discord form. The character's original career ending
and the campaign's private death-limit receipt persist together. Reopening the
database pool and replaying the command returns the saved result. A later
confirmed lethal choice is rejected after an earlier campaign death, and the
player can still choose a supported nonlethal outcome. A fatal event with no
owned Defeat proof also fails through the common canonical writer.

Tests used the temporary workspace selector runner described in
[calendar verification](ASYNC_CAMPAIGN_TIME.md). The matching selection on a
regular environment is below.

```bash
.venv/bin/pytest -q tests/rules/test_campaign_opening.py \
  tests/rules/test_defeat_service.py tests/rules/test_defeat_runtime.py \
  tests/rules/test_severe_punishments.py tests/rules/test_reign_pc_execution.py \
  tests/test_m2_game.py tests/test_session_zero.py
```

Verification covers the offline engine and Discord SDK flow.

## Combined candidate

The integration starts from `81fa968` on `codex/narrative-death-integration`.
The ZIP passed its integrity check and all nine manifest hashes matched.
The two timing patches were already represented by `b79090e` and
`6a9af80` with later Activity and Director changes on top. The remaining
three patches were integrated. The new rules opening service lives in
`campaign_difficulty.py` so that the existing Activity brief service can
continue using its own contract. The shared calendar calls the current
scene-close API. The reconciliation keeps the current Girl command
structure, career-aware creation review, managed Activity startup,
Soldier Defeat option, and Harpy capture fields.

The first combined run found a mismatched scene-close signature during
introductory day advancement. After repair, the focused opening, Session
Zero, Defeat, calendar, Activity engine integration and native registration
selection passed **38 tests in 38.74 seconds**. A follow-up covering the
opening, severe punishments, Reign execution and Activity engine integration
passed **15 tests in 22.40 seconds**. These selections overlap.

The manifest-verified Activity snapshot and both overlays passed **4
simulated checks in 18.93 seconds**. The Defeat field test uses the
original Pilot's real saved outcome and exercises both an available and a
spent Narrative exception. These results are separate from the 104 checks
reported by the supplied package. See the
[Activity handoff](../integrations/activity/P2_SESSION_UI_HANDOFF.md#campaign-difficulty-and-session-zero)
for the required Session Zero controls and the supplied ports.

The active Activity runs from the separate Windows checkout. Reconcile these
ports onto its maintained routes and client files before deployment. The
November 16 snapshot predates the current interface and serves as an offline
test base. Authenticated Discord, a full repository regression, and cutover
are pending.
