# CONSUME Feral low → actual Disobey continuation (r270)

## Diagnosis
The r269 legacy test expected completion immediately after roll delivery. It omitted the ordinary participant Tag window and the original Handler's discovery decision. The same failure was reproduced on r268 by the root. Passing the Tag window alone correctly exposed the remaining Handler choice. No production defect or deadlock was established.

Printed Feral (PDF67/printed65) makes Disobey results low while the granted Tag remains. Printed Disobey (PDF23/printed21) still allows later Handler discovery/Punishment on a low result. The source-backed implementation preserves that decision: `m3_consume.apply_disobey_limit` applies the effective cap after final Tag total; `m2_choices` requests `handler_disobey` on low and completes only after its authorized response.

## Bounded test correction
Only `test_real_feral_source_tags_bonuses_and_required_original_owned_continuations[low]` is changed. Use a real high natural Disobey roll, pass participant Tag choices, assert low effective total 7 and no successful actor refusal choice, then have the actual Handler record no discovery. Assert completion, unchanged raw roll receipt, and continuing Feral Tag/effect. No fabricated consequence, new roll, auto-discovery decision, production guard change or registry approval is introduced.

Worker authored only; root executes and records outcome separately. The fixture uses synthetic approval/setup and service calls. This is not live Discord, all-type coverage, full regression, full privacy, process restart or backup/restore proof. Prior failed logs remain historical evidence.
