# Offline precise mission timing verification

Incremental base `2228ce7e35764b3b7f390762f327c1688f8903fa` is the
offline calendar implementation. The package manifest records the exact
follow-on commit and the original base for applying both patches.
[Integration and projection contract](../docs/work_orders/PRECISE_MISSION_TIMING.md)

| Scope | Executed result |
|---|---|
| Precise timing feature | 7 passed in 7.65 seconds on the final timing snapshot |
| Affected suite | 126 passed in 68.68 seconds across precise timing, chapter cuts, missions, scene work, and native M2 Plays |
| Configured CI selection | 39 tests collected successfully |
| Changed Python checks | Ruff lint and format passed for seven files. Scoped mypy passed for six source files. |
| Repository safeguards | Repository scan passed with zero findings. |

The route cases commit the 15-minute tunnel at 18:35 and the 25-minute escort
at 18:45. Exact arrival at 18:40 misses a strict cutoff and satisfies an
inclusive cutoff. The missed-deadline consequence records once. The unknown
cost and consequence case preserves the Handler blocker, rejects a stale menu
and rolls back a forced failure before committing time.

The timed native Keep Your Head case saves one original dice receipt and one
linked timing event, reopens the database pool, replays the roll and completes
the Pilot and Handler responses. The clock advances once. Parallel participants
select independently at 18:20. Their saved choices and a later Handler rejoin at
18:38 exercise choice ownership, safety pause, stale confirmation, and
audience filtering.

## Reproduction

Use the existing locked environment. The temporary asyncio selector wakeup
runner in the [calendar verification report](ASYNC_CAMPAIGN_TIME.md) was
used for tests that exercise the existing async delivery worker in this
workspace. The test commands below also work with the normal runner on a
host with working selector wakeups.

```bash
.venv/bin/pytest -q tests/rules/test_mission_timing.py
.venv/bin/pytest -q tests/rules/test_mission_timing.py \
  tests/rules/test_campaign_time.py tests/rules/test_mission_service.py \
  tests/rules/test_scene_work.py tests/test_m2_game.py
```

The affected suite preceded the final addition of projected arrival fields.
The final timing suite exercises those fields and the underlying committed
outcomes. Remote CI, the full repository suite and live client testing
remain outside this evidence.
