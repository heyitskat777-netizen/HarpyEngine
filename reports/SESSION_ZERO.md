# Session Zero verification

The incremental base is HarpyEngine commit
`1551083c2111bea2bf83488c893796467f730ac2`. The integration package records the
exact Session Zero commit. [Setup and workflow](../docs/work_orders/SESSION_ZERO.md)

| Scope | Executed result |
|---|---|
| Final Session Zero and SDK registration selection | 4 passed in 2.48 seconds |
| Affected suite | 145 passed in 20.16 seconds across Session Zero, Handler setup, character creation and review, Pair Assets, onboarding and read-only bot |
| Configured CI selection | 43 tests collected successfully |
| Changed Python checks | Ruff lint and format passed for 11 files. Scoped mypy passed for nine source files. |
| Repository safeguards | Repository scanner passed with zero findings. |

Synthetic members approve the exact Handler proposal and retain separate
authority for the final appointment. A revised proposal invalidates old
approvals. Every listed Pilot attaches an existing complete saved review or
active sheet. A changed review blocks worksheet generation until the owner
refreshes it. The generated worksheet includes owner-entered campaign prompts
and the Handler's goal draft. Private sheet and Bond details stay out of the
download. A nonparticipant cannot generate it, and a change of membership
requires fresh contributions for the new group.

A native Discord component test opens the real private panel and activates
the Generate button against two active sheets. It inspects the actual Markdown
attachment and private interaction response. This is offline SDK coverage.

The initial startup test reproduced a duplicate Mentor registration on the
unmodified base. That group also declared 30 direct commands. Six M3 controls
moved under `/campaign pilot`; the existing Mentor nomination retains its
original path. The final SDK test validates both Mentor routes and Discord's
25-command group limit.

The [calendar verification report](ASYNC_CAMPAIGN_TIME.md) describes the
temporary selector wakeup runner used for existing async SDK tests in this
workspace. The following command runs directly on a host with working asyncio
thread wakeups.

```bash
.venv/bin/pytest -q tests/test_session_zero.py tests/test_handler_setup.py \
  tests/test_creation.py tests/test_creation_review.py tests/test_pair_assets.py \
  tests/test_onboarding.py tests/test_read_only_bot.py
```

The affected suite preceded the final Handler player-name line in the
worksheet. The final selection verifies that line. Remote CI, live guild
registration and human playtesting remain outside this evidence.
