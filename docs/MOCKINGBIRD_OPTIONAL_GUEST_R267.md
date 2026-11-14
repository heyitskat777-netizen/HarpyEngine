# r267: Mockingbird Call boarded guest's optional choice

## Verified ordinary blocker and correction

Source: locally inspected *Girl Frame 2026_09_01 (1)*, printed p33 / PDF p35. Call of the Void permits a cockpit guest and makes that guest's additional choice optional. Recovered r266 `services/m3_mockingbird_communion.py` boarded an accepting guest, then required an effect. Invitation refusal instead prevented boarding, so it did not implement boarding without an extra effect.

The r267 service adds `decline_effect` only at the already guest-owned effect stage, before any mechanical effect has been applied. It accepts only the guest's account, records an actual choice/completion event, and completes the source continuation. It does not unboard, alter resources, refund a roll, or fabricate a mechanical effect. Native controls expose “Stay aboard without an extra Dive choice.” Existing invitation refusal and actual effect selection remain unchanged. A committed effect in table/NPC/threshold phases cannot be skipped by this operation. A rejected uncommitted table proposal can return to the effect stage as before.

## Files and focused evidence

- `src/girlframe/services/m3_mockingbird_communion.py`
- `src/girlframe/discord_adapter/m3_mockingbird_communion.py`
- `tests/rules/test_mockingbird_optional_guest.py`

New authored normal-path test: actual Call invitation and real boarding, wrong-controller and effect-smuggling rejection, native mocked form opt-out, unchanged sheets/placements/passengers/cast, real continuation completion, same receipt and one dice call, stale revision rejected. Worker did not run pytest. Changed-file Ruff and AST parsing passed. Two initial test line-length warnings were corrected by formatting; no gameplay result claimed from static checks.

The harness inherits temporary test-only rule approvals and synthetic setup from `test_mockingbird_communion.source`; it is not production approval, Discord dispatch, AI Director, process-restart or all-type proof. Root must run the focused test after integration. Existing guest-effect and invitation-refusal tests are authored unaffected-path evidence, not newly executed here.

## Bounded ordinary branch reconciliation

Fresh printed p33 compared with current source and authored assertions:

- Person mid three, high four plus owned counterpart Tag, low up to two plus owned Tag/departure permission: `engine/m3_mockingbird.py:choose_capabilities`, `services/m3_mockingbird_plays.py:apply/release/end`, native `m3_mockingbird_plays.py`; authored `test_mockingbird_person.py` covers these branches. No additional mismatch established. Native low controls are mocked; physical movement outside these conversation controls was not exhaustively audited.
- Risk Factor: actual Void cost shifts one retained receipt to an owned 8/9/10; `engine/m3_mockingbird.py:risk`, `engine/m3_void.py` threshold admission and `resolve_mockingbird`, authored `test_mockingbird_risk.py` and `test_mockingbird_call.py`. Immunity differs inside the fully altered original Frame; genuine linked Keep outcome is required. No additional mismatch established; tests not rerun.
- Call reclassification: `services/m3_mockingbird_call.py:effect/apply` uses real original assets and authoritative classification. Authored `test_actual_native_dive_classification_moves_both_directions_once` checks IDs, family changes, preserved damage/Void and receipt. No new execution claim.
- Call boarding: `services/m3_mockingbird_communion.py:respond/_effect` applies physical boarding, guest-owned optional real consequence and its required followups. Optional no-effect gap corrected here. Authored accepted guest test applies real Identity erasure and awaits original table replies; native guest test uses injected form values.
- Call Gorgon relay: source nearby/known cast validation, original controller response, filtered correspondence; authored `test_actual_nearby_gorgon_owns_reply_without_new_roll_cast_or_compelled_truth`. No compelled truth or generated Director response. No new execution claim.

These checks replace uncertain catalog headings with named branches; they do not certify every consequence, combination, printed rule or release gate. Sex retained prior branch map is not freshly certified here. Production registry and campaign approvals remain unchanged. Final candidate reconciliation, full regression and privacy/migration/restore/live Discord checks remain pending. No merge or deployment.
