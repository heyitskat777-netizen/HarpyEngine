# Nested Keep Feedback: native delivery verification

## Exact bound

This is a verification-only follow-up to the r234 nested Feedback source. The
baseline is independently copied from the verified current local source with
path/content SHA-256
`e70e0efc93a24065d2df7cdf71f6fc7c2ce6faec1542918047149cbddba3c36e`.
All 1,813 source files match before editing; copies do not share file inodes.
Only the existing normal test and this report change. No production behavior,
release gate, shared registry, native routing or historical report is changed.

The prior root-reported accepted-purpose normal passed, but its direct
`game.roll` fallback made that result insufficient evidence for automatic native
child delivery. This revision removes that fallback. It requires the real
GameWorker to discover the persisted native child, commit its final-Identity
Feedback hold, and resume the exact held Play after its human-owned purpose and
Identity decisions. A missing dispatcher result now fails rather than being
replaced by a test call.

## Rules and delivery contract

Read the retained official Girl Frame 2026_09_01 rulebook directly at PDF pages
10, 21, 22 and 84 (printed 8, 19, 20 and 82). This preserves the existing source
interpretation: marking the newly granted last unmarked Identity triggers
Feedback before the actual Keep roll, while the earlier Beneath pin and its
already committed effects remain. No rulebook or extracted text is copied into
source or evidence.

The implementation contract is the existing native `open_play` confirmation,
`GameWorker.advance`, `GameService.roll`, and Ankou `resume_inputs`. A newly
constructed worker reads the saved child without re-confirming human choices.
The test observes the actual `m2.confirmed_roll:` command and the original
Pilot's committed Feedback event; it then requires the distinct
`m3.ankou_resume:` command containing that exact committed mark. The child has
exactly one saved roll receipt when accepted and none when refused. Direct
service calls remain only for already-completed receipt retries, after worker
progress and owned effects are established. Service/worker reopening is not
process restart or backup/restore evidence. The synthetic gateway is not live
Discord delivery evidence or an exactly-once Discord promise.

The existing normal still checks original parent receipt and pin preservation,
owned human choices, unchanged Heat/Identity commitment, source ancestry,
private Feedback visibility, safe public messages, final Handler judgment,
parent completion, retries and final scene-lock release. The refused-purpose
parameter remains authored and requires no resume command or fake receipt.

## Focused validation

Root minimum node:
`tests/rules/test_ankou_nested_pin_feedback.py::test_native_nested_pin_keep_feedback_preserves_both_sources[True]`

Deferred sibling:
`tests/rules/test_ankou_nested_pin_feedback.py::test_native_nested_pin_keep_feedback_preserves_both_sources[False]`

Worker pytest and collection: **NOT RUN**. Root runtime and bounded independent
review: **PENDING**. Ruff check and format check passed for the single changed
Python file. AST parsing passed without imports. No production source types
changed, so source Mypy is not applicable. The external evidence packet records
commands, source provenance and frozen patch verification. The prior pass is not
relabelled as a pass for this stronger normal.

Other parent Feedback outcomes, high-pin compositions, counterpart and
learned/piloted/directive variants, other tests with direct-roll fallbacks, final
P1 regression/global static/migration/privacy/restore checks and actual human
acceptance remain separate or pending. This packet does not close the ordinary
P1 backlog. RULES_SUBSET; bot OFF. No installation, bot execution, live Discord,
deploy, merge, publication, model call, private-engine write or full regression.
