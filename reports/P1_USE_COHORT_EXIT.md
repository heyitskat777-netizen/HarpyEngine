# Per-actor NPC use cohort exits

Baseline: final isolated `harpyengine-p1-use-cohort-20261110` (v11), including
v9 protection cohorts and v10 actual NPC use. This is additive, not a replacement
for those earlier layers or a bare published-checkpoint patch. Unknown paused
unpublished Easy Target changes remain an unverified collision risk.

## Playable behavior

Easy Target PDF41 / printed39 grants the cohort exemption for actually going
along. Nomination does not establish performance. Superseding v11's all-cohorts
completion gate, the actual NPC may record completion while a nominated cohort
has not answered. Only that cohort's original controller can subsequently
acknowledge missed participation; the pending choice is not auto-consumed.
Before completion and after Handler validation, the original cohort may instead
explicitly decline. Both nonparticipation outcomes preserve the owned account,
source, outcome and event; neither grants performance, exemption or a penalty.
Actual participation still requires available co-present original bodies, and
actual participants retain their exemption. If nobody participated, the existing
Newgirl-owned optional Bond choice stays intact. A late acknowledgment cannot
retroactively erase that choice or create an exemption. Earlier declined records
retain their completion event rather than being rewritten at NPC completion.

Native private controls distinguish participation/decline from the later missed
acknowledgment. Stale pre-completion participation submissions fail closed.
Historical proof binds exact owned response and immutable birth facts; missed
outcomes additionally prove the actual completed NPC use. Existing participation
facts decode with the participated default. No migration or shared dispatch
change. Other rolled/performer-specific source boundaries remain explicit.

The parent Easy Target action remains pending until all original obligations and
optional Bond choices are actually answered. This is intentional durable human
agency, not permission for another controller or a timeout to fabricate an answer.
Persistent unavailable actors remain a human-facilitator situation. No fictional
punishment, reward, intimate consent, dice, injury or unrelated effect is invented.
Interpretation remains delegated and requires printed-rule clarity review.

## Verification

Authored two parameterized native normal episodes in
`tests/rules/test_use_cohort_exit.py::test_native_multiple_cohorts_decline_and_miss_use`:
- Mixed actual participation, explicit decline and later missed acknowledgment.
- All nonparticipants, preserving and answering the original optional Bond choice.

Both preserve receipt/dice/sheets/world, exact declined completion, pending actor
agency, original primary consequence, durable private readback and outcome proof.
The existing native helper submits duplicate confirmation. The existing v11
participation normal was updated only to select the new native outcome field.
No worker pytest or collection. Root subsequently ran the exact new exit node:
**2 passed in 7.84s**. No Python changes followed that result. This focused
result is not whole-candidate regression or human acceptance.

Executed on the final five changed Python files:
`harpyengine-p1-adapter-20261109/.venv/bin/ruff check`: All checks passed.
`harpyengine-p1-adapter-20261109/.venv/bin/ruff format --check`: 5 files already formatted.
An initial lint pass found one overlong UI string; fixed before the final checks.
No installation, bot startup, model calls, live Discord, deployment, merge,
private-engine writes or remote publication. Independent review,
whole-candidate regression/global gates and actual player acceptance remain pending.
Keep bot OFF and RULES_SUBSET.
