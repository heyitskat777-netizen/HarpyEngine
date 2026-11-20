# Campaign opening verification

The incremental base is Session Zero commit
`7b8afdb08bdb51869a9901f5709cf7d686aaeb31`. The integration package records
the follow-on commit and the original base. [Campaign opening workflow](../docs/work_orders/CAMPAIGN_OPENING.md)

| Scope | Executed result |
|---|---|
| Feature and affected regression suite | 81 passed in 65.67 seconds across opening, Session Zero, calendar, mission timing, missions, Defeat, discipline, Reign and scene work |
| Configured CI selection | 47 tests collected |
| Changed Python | Ruff lint and format passed for 20 files. Scoped mypy passed for 19 source files. |
| Repository safeguards | Repository scan reported zero findings. |

The new opening fixture changes a plan after a vote, rejects the stale
approval, checks the native completion modal, completes with pre-activation
saved sheets, and replays after reopening the database pool. The group sees
the actual Handler introduction and no Pilots are joined automatically. In the
Hard fixture each of three fictional days is Handler-advanced and recorded once.
The first mission remains unavailable until Day 4. Dispatch binds a playable
scene for the exact accepted participants. Existing mission-end work settles
before escalation. The next Hard briefing requires its extra obstacle and
invited players see it before acceptance.

Narrative rejects Execution, Lobotomization and Indefinite Imprisonment in
the real discipline path. That fixture resolves a supported nonlethal
Punishment. A real low Defeat retains its saved dice and original character
after a rejected death choice, then resolves a player-chosen survival outcome.
The common canonical writer also rejects a fatal archive submitted through a
different event path. Legacy printed outcomes exercise the default Normal
behavior in the affected regression cases.

The testing workspace used the temporary selector wakeup runner described in
[calendar verification](ASYNC_CAMPAIGN_TIME.md). In a regular environment the
checks run directly with pytest.

```bash
.venv/bin/pytest -q tests/rules/test_campaign_opening.py tests/test_session_zero.py \
  tests/rules/test_campaign_time.py tests/rules/test_mission_timing.py \
  tests/rules/test_mission_service.py tests/rules/test_mission_ui.py \
  tests/rules/test_defeat_service.py tests/rules/test_severe_punishments.py \
  tests/rules/test_role_punishments.py tests/rules/test_reign_pc_execution.py \
  tests/rules/test_scene_work.py
```

The initial targeted run exposed the handling of apostrophes in the worksheet
and the test's missing required mission-end discipline action. Both are covered
by the final passing selection. Live Discord registration, Activity wiring,
and the full repository suite remain outside this evidence.
