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
