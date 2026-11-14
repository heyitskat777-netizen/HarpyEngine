# P1 Check Sensors: classify questions, not controls

## Scope and source

This isolated correction is based on the reviewed local r235 source snapshot
`983d6f71afb78bea95402abe7b665cda229595271d4f7367d0a3be512ead1f3e`.
It is not a deployment, rules-complete claim, release approval or live Discord result.

Authority: *Girl Frame 2026_09_01 (1).pdf*, PDF page 26 / printed page 24,
“Check Sensors,” as independently checked in the source handoff. The six stable
question IDs now have one shared printed-text mapping, preserving the Foundation
and satellite qualifiers. No PDF or real campaign data is included.

## Changes and boundaries

- Exact printed text and stable listed IDs classify as listed, regardless of
  dropdown versus text-field entry. Matching allows whitespace differences only;
  shortened former labels, paraphrases and case changes are not invented aliases.
- New listed text is saved as its existing stable ID. Mixed entries retain the
  existing order: selected IDs, then q1/q2/q3 in order. Human answers remain a1,
  a2, a3 in that same order. Genuine custom text is retained unchanged.
- Low still requires one listed question. Its native form remains listed-only;
  an exact listed question supplied in a typed/API field is also listed. Mid
  requires two, high three. A genuine high off-list question still requires
  exactly one original consequence, including the actual later Punishment
  obligation when chosen. No answers or choices are inferred.
- Human Hound remains a separately authorized appended question, outside the
  ordinary quota and classification. This does not grant its source to an
  ordinary custom question with the same text.
- A pending Handler decision derives classification from the stored ordinary
  questions, ignoring an older erroneous control-based flag. Projection is
  read-only. The owned response records the corrected flag within its existing
  transaction, without rerolling or replaying effects. Completed actions and
  existing obligations are not migrated, deleted or rewritten.
- Dropdowns use full printed wording. Numbered Handler readback resolves legacy
  stored IDs and escapes Markdown and mentions in genuine custom questions.
  Handler authority, complete-answer validation, private delivery and explicit
  confirmation remain in the existing paths.

Changed implementation: `engine/m2.py`, `services/m2_choices.py`,
`services/m2_game.py` and `discord_adapter/m2_ui.py` under `src/girlframe/`.
Tests extend `tests/test_m2_game.py` and `tests/test_m2_ui.py`.

## Authored regression coverage

- Both high-result printed-question triplets submitted entirely as text, with
  no consequence control, complete owned answers, no Punishment and one roll.
- Mixed listed/text order, conservative whitespace and restart of a synthetic
  old pending decision with a wrongly true flag; readback causes no storage write.
- Low listed-only/count and mid two-question/custom behavior. Existing
  dropdown-only tier cases are unchanged.
- Existing two high off-list consequence branches now each include one genuinely
  custom question alongside listed entries. Missing and multiple consequences
  are rejected; actual Punishment creation remains asserted.
- Exact dropdown wording, safe numbered pending readback, and separate appended
  Human Hound classification. Existing real Human Hound service coverage remains.

All gameplay tests and test collection are **NOT RUN by this worker**, following
the active P1 testing instruction. Suggested root minimum:
`tests/test_m2_game.py::test_high_sensors_printed_custom_questions_are_listed[foundation-and-satellites]`.
The remaining authored normals stay for final integrated verification; do not
interpret static checks as gameplay evidence.

## Executed verification

Reused the existing pinned environment without reinstalling dependencies.

- Full baseline inventory verified before copying: 1,816 files, exact source
  digest above. Only manifest-listed source files were copied. Disk and inode
  headroom were checked before copying.
- Ruff lint and format checks: **passed on all six changed Python files**.
- Mypy with `MYPYPATH=src`, `--follow-imports=silent`: **passed on all four
  changed source files**. This is scoped typing, not the global final gate.
- In-memory AST parse: **passed on all six changed Python files**, with no
  application imports, pytest or test collection.
- One UI test fixture omission (`own`) was found during static source inspection
  and corrected before freezing. Its lint/format checks passed afterward.

Final independent review, integrated smoke/full regression, global static,
applicable privacy/migration/restore checks and actual player acceptance remain
pending. Bot OFF; no commit, push, merge, deployment, model call or live data action.
