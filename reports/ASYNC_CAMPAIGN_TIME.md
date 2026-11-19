# Offline campaign-time verification

Base revision `c4550ecbd89bbf84363537e7bdf763c2177a998f` matched GitHub `main`
during inspection. The integration package records the exact local source commit.
This is a bounded synthetic slice under the existing M3 RULES_SUBSET policy.
The [work order](../docs/work_orders/ASYNC_CAMPAIGN_TIME.md) records the source
seams, printed rules anchors and Campaign UI contract.

| Scope | Executed result |
|---|---|
| Feature suite, `tests/rules/test_campaign_time.py` | 4 passed in 9.77 seconds on the final feature snapshot |
| Affected regression suite | 142 passed in 109.86 seconds across scene work, Off-Duty cycle, Medical, actor service, shared recovery and M2 gameplay |
| Standard pytest runner | The two feature cases without async delivery passed in 2.82 seconds |
| CI selection | 31 tests collected successfully from the configured selection |
| Changed Python lint, format and types | Ruff lint and format passed for six files. Scoped mypy passed for five source files. |
| Existing CLI and schema | Help and temporary SQLite health passed, schema upgraded to head and Alembic found no new upgrade operations |
| Registry and repository safeguards | Registry remained RULES_SUBSET. Original planning package verified and repository scan reported zero findings. |

The feature suite uses the existing Defeat and Medical services for a real
pending recovery decision. It also references the original answered Play choice
and its saved receipt. Two pilots can hold parallel bookings without implied
attendance. The Handler's blocked cut races the owned Medical exchange, then
commits on a fresh preview. A failure after preparing the cut rolls back the
cut and playable-scene closure. Reopening the database pool and replaying the
command returns the original receipt. A private late grant reaches its named
recipient and a proposed late injury/roster change stays in Handler review.
The existing explicit Off-Duty test workflow saves the three base Strain checks,
recovery and one world advancement under the original period identity. Replaying
the period finish and skipping three fictional days introduce no new effects.
The suite also exercises the safety pause, stale preview, release gate,
nonoverlapping audience scopes and legacy cross-campaign views.

## Reproduction

The configured installer stalled on a restricted package-index connection.
The lockfile and existing cache rebuilt the editable package with
`uv --offline --cache-dir .cache/uv sync --locked --all-groups`.

The workspace's default asyncio selector also stalled waiting for thread
notifications on the unchanged Medical regression. The async tests ran through
a temporary runner that periodically wakes the selector. The tests, engine
worker, network-blocking fixture and standard CI command are unchanged. Run
the following selections directly on an environment with working asyncio
thread wakeups.

```bash
.venv/bin/pytest -q tests/rules/test_campaign_time.py
.venv/bin/pytest -q tests/rules/test_scene_work.py tests/rules/test_off_duty_cycle.py \
  tests/rules/test_medical.py tests/rules/test_actor_service.py \
  tests/rules/test_shared_recovery.py tests/test_m2_game.py
```

For the same workspace condition, invoke the selections through this local
test runner outside the repository.

```python
import asyncio
import sys

import pytest


class WorkspaceEventLoop(asyncio.SelectorEventLoop):
    def _run_once(self):
        wake = self.call_later(0.01, lambda: None)
        try:
            super()._run_once()
        finally:
            wake.cancel()


policy = asyncio.DefaultEventLoopPolicy()
policy._loop_factory = WorkspaceEventLoop
asyncio.set_event_loop_policy(policy)
raise SystemExit(pytest.main(sys.argv[1:]))
```

The full repository regression, remote CI, live client verification and player
acceptance remain outside this evidence. The next implementation step is the
opt-in precise mission sequence and exact cutoff acceptance.
