# Owned NPC protection cohort decline

Baseline: `harpyengine-p1-dive-hurt-integrated-20261111`. Actual source inspection
confirmed that NPC use, hurt and protection cohorts already exist. The concrete
missing normal branch was an original protection cohort's owned nonparticipation:
only actual participation and missed-after-failure were supported. This slice does
not redo other cohorts or treat stale queue text as missing implementation.

Source: Easy Target, rulebook PDF41/printed39, matched against the local current
source and existing registry. High-result going along exempts actual participants;
nomination is not participation. The delegated interpretation extends the existing
use/hurt owned decline policy to original NPC protection. Clarity review remains
pending, recorded in `easy_target_cohort_scope` revision 3 and CAMPAIGN_RULINGS.

After original Handler validation, the original controller may decline before or
after the actual NPC protection, but not after its failure. This immutable private
answer closes only their obligation. It supplies no body/performance/exemption and
does not alter the primary, sheets, world, known roll or receipt. The NPC still
performs actual protection; its later actual failure retains the Newgirl's optional
Tag. After failure an unanswered person owns the existing missed acknowledgment.
Original no-option participation/missed responses remain valid. All three outcomes
now have private source-proved historical native readback. No migration is needed:
the existing fact model gains an optional protection reference only for pre-source
declines and the explicit declined outcome.

The original controller remains necessary. Existing durable facilitator requests
can coordinate returning-controller recovery, but cannot manufacture decline or
participation, waive another person's choice or auto-close indefinite absence.
No general authority, timeout, generic NPC roll or new body type is introduced.

## Files and verification

Changed production modules: `engine/m3_easy_target.py`,
`services/m3_easy_target.py`, `discord_adapter/m3_easy_target.py`.
Changed evidence: the new `tests/rules/test_protection_cohort_decline.py`, this
source checklist, CAMPAIGN_RULINGS and the existing registry ruling/test evidence.
Root retains shared integration/publication ownership; this is an isolated copy.

The one authored native episode uses actual high source/reactions/Handler validation,
an early NPC decline and post-performance Pilot decline, then an actual Handler
failure, remaining original controller's missed answer and Newgirl-owned failure
Tag. It verifies unchanged primary on decline, original receipt/dice, no fabricated
exemption, unauthorized answer rejection, stale post-failure rejection, private
canary and historical native readback after a real scene change. Initial bodies,
roles/resources are synthetic fixture setup; outcomes are real service/native calls.

Worker commands, run against the isolated candidate using the existing environment:
- `ruff format` on all four changed Python files: two reformatted, then four unchanged.
- `ruff check` on all four changed Python files: all checks passed.
- `mypy --follow-imports=silent` on the three production modules: success, no issues.
- No pytest or collection by the worker.

Root reported the exact new node passed **1 in 5.04s**:
`tests/rules/test_protection_cohort_decline.py::test_native_protection_cohorts_decline_before_and_after_performance`.
No Python file changed after that result. Other participation/hurt/use/facilitator
normals were not rerun; final full regression and global static/migration/privacy/
restore, independent review, human testing and owner acceptance remain pending.
Bot OFF; RULES_SUBSET. No deployment, merge, model calls or private-engine writes.
