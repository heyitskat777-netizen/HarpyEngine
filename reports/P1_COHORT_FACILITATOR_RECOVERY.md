# Unavailable cohort facilitator recovery boundary

Baseline: `harpyengine-p1-use-cohort-exit-20261110` (v12). This isolated
candidate changes no production Python, mechanics, registry or source rulings.

## Finding and actual recovery

The existing `/facilitator request` accepts the real pending Easy Target action
from its actual participant. Select that action and the Easy Target rule, state
the unavailable-controller issue, and explicitly choose whether to share the
request with the configured human facilitator. The request persists the source,
source/state revisions and original receipt. Private adjudication and the
requests inbox retain the human ruling. Configuration is an explicit authorized
setup action, not inferred from fictional Handler or administrator status.

The facilitator may record the blockage. Once the original controller can
respond, select the existing-source route and let that controller reopen their
original cohort choice. After NPC use completed, their actual missed-participation
acknowledgment closes only their owned response. The existing-source route permits
that original action to proceed despite the adjudication hold. Only after the
original action completes can the facilitator/requester resume the adjudication.
No additional roll, changed result, invented participation, exemption or consent
is needed. Existing v12 native controls already provide this owned response.

**Important limitation:** this is not a way to unblock a permanently unavailable
actor. The pending owned choice and parent stay unresolved while that person is
absent. A mandatory action cannot be declined or completed by a fiction-only
ruling. An existing-source ruling alone also cannot resolve the action. No
facilitator waiver, substitute answer, timeout or administrative force-close is
implemented. The human path provides durable coordination and eventual owned
recovery, not unconditional liveness.

This follows `docs/work_orders/P1_PLAYABLE_RELEASE.md`, escalation items 5–7:
retain original mandatory work and choices, preserve printed ownership and
consent, and resume only after a supported real source effect. Original handoff
AGENTS agency and canon boundaries also apply. Solving indefinite absence would
need an explicit product/source policy for suspension or retirement of the
unanswered obligation without representing an answer or changing known results.
It cannot be claimed as already solved by the escalation form.

## Evidence and scope

Relevant existing implementation:
- `services/p1_facilitator.py`: `_source`, `request`, `candidates`, `change`,
  `require_scene_clear`. Mandatory/fiction-only/decline guards and exact original
  action completion/receipt checks remain unchanged.
- `discord_adapter/p1_facilitator.py`: native actual-source request, private
  ruling and existing-source recovery.
- `tests/rules/test_facilitator.py`: existing notice/privacy/source recovery.
- `tests/rules/test_use_cohort_exit.py`: original native cohort missed response.

Added one normal scenario at
`tests/rules/test_cohort_facilitator_recovery.py::test_existing_facilitator_recovers_only_after_original_cohort_response`.
It starts with real completed NPC use and one unanswered original cohort; uses
a different explicitly configured facilitator; checks that decline, fiction-only
and premature resume cannot substitute an answer; then runs the returning original
controller's native response and resumes the original action. Assertions preserve
the primary result, sheets/world, receipt, dice and lack of a missed exemption.

Worker verification: Ruff formatting and `ruff check` passed on the new test.
Worker ran no pytest or collection. Root subsequently ran the exact new node:
**1 passed in 4.19s**. No test or production Python changed after that result. Existing native
entry wiring was source-inspected, not an actual Discord interaction. No new
runtime functionality is claimed. Final regression, global gates, independent
review and human acceptance remain pending. Bot OFF; RULES_SUBSET; no deployment,
merge, publication, model calls or private-engine writes.
