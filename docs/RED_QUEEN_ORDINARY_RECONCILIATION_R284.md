# Red Queen low Consult: actual sequential advice Orders, r284

## Source and scope

Authorized local `Girl Frame 2026_09_01 (1).pdf`, PDF page 89 / printed 87,
reopened for this run. Low Consult recalls one AM/unmarks it, assigns someone
else the Queen, and requires advice from the AMs still assigned to the original
actor. That advice counts as Orders. Player responses cannot be fabricated.
Existing r265 ordinary Consult/Panopticon map remains; this is one completed
normal consequence path, not certification of every Red Queen Play or branch.

## Demonstrated blocker and fix

The new native-form low Consult workflow reproduced `Preserve the actual held
original Consult action` when the Handler supplied the next required advice,
even after the original owner had actually followed the first Order. The source
retained its current Order pointer, and the synchronizer rejected any pointer.

`m3_red_queen_support.issue_pending_orders` now permits progression only when
that prior pointer proves an Advice belonging to the same original Consult and
actor, with original author and exact instruction/authority metadata. The actual
campaign-scoped Order row must match issuer, target and scene and be `followed`.
Any pending source decision blocks progression. Each original Advice keeps its
own Order ID and answer event; only the parent's current pointer advances.
No new Order can overwrite an unanswered response. No roll, answer, obedience,
consent or resource effect is invented. A refusal is not treated as obedience.

## Evidence and limits

Root owns runtime results. New selector:
`tests/rules/test_red_queen.py::test_low_consult_all_advice_owned_orders_complete_original_play`.
Initial union reproduced failure (1 failed, 1 passed, 7.35s); root corrected
focused run passed 1 in 4.26s and root scoped Ruff passed. The test uses native owned recall/transfer
and Handler advice forms, real four source-bound Order rows, independently owned
obedient responses, rejection/rollback of overlapping advice and unauthorized
authorship, original receipt/one roll, final completion and in-process rebuild.
The prior parametrized low/high test was corrected to answer each actual Order;
it is not an additional runtime pass this run. Scoped Ruff passed.

Synthetic starting world/resources and test-only approvals, direct form values,
mock interactions/service response commands remain. Not live Discord, whole-DB
restore, exhaustive privacy or full regression. Refused/disobeyed advice after
child completion remains outside this new sequential-followed proof and is
fail-closed by the added guard; do not claim all low Consult response combinations.
No rules interpretation or legitimate approval changed. Ordinary type evidence,
pre-pause checkout reconciliation and exact final-candidate release checks remain.
