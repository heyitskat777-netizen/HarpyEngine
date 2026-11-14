# r256: owned ANKOU Bond-rewrite target selection

## Scope and provenance

Baseline: verified Space r255 v24; isolated source only. No publication/deployment, bot remains off. The retained printed-rule audit in `reports/P1_ANKOU_BOND_PIN.md` identifies Girl Frame 2026_09_01 PDF84/printed82: the Pilot cuts an actual Bond and rewrites it as an Asset. `tests/rules/test_ankou_married_bond.py` and the existing authoritative service retain the separate marriage source protection. Printed PDF was not re-opened for this UI change; no new rule interpretation or marriage behavior introduced.

The native Feedback form previously used one undifferentiated scene-person selector for Bond, purpose and reprisal. It offered people with no current Bond and protected spouses as if usable for a Bond rewrite, even though authoritative submission rejected them. It now has a dedicated eligible Bond selector. Purpose/reprisal continue to expose actual scene people, including a spouse; the player still selects the effect and person. No consent or response is inferred.

A shared `_bond_target_blocker` supplies both projection and authoritative write-path checks. The write recomputes eligibility against transaction state, retaining prior error messages and depth-before-marriage ordering. Only the original resource owner's projection includes this data; no privacy scope change. The native adapter passes `bond_target` as the existing engine `target`; direct service commands are unchanged. Existing native Bond UI fixtures were updated for the new field.

## Changes

- `src/girlframe/services/m3_ankou_feedback.py`
- `src/girlframe/discord_adapter/m3_ankou_feedback.py`
- `tests/rules/test_ankou_bond_replacement_ui.py`
- `tests/rules/test_ankou_married_bond.py`

## Verification

Worker pytest/collection NOT RUN, per workflow. Root normal suggested: `tests/rules/test_ankou_married_bond.py::test_married_ankou_rewrites_only_actual_outsider_bond_and_preserves_marriage[last_identity]`. It establishes an actual marriage, proves server spouse rejection, checks spouse excluded only from Bond targets and outsider included, then completes the real outsider Bond rewrite while preserving marriage/permissions. Existing free-slot UI test amended for the dedicated selector and verifies used Bond is no longer eligible.

Worker Ruff on the four changed Python files: initial E501 line-wrap error corrected; final all checks passed. Full regression, live Discord, stale-selection runtime case and other Feedback sources are not newly verified. This is a bounded native selector fix, not global P1 completion or all Frame coverage. Published integration and pre-pause unpublished overlap remain for root reconciliation.
