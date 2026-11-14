# CONSUME actual Clone AM lifecycle: r260 source review

2026-11-13. Read-only audit of verified r260 v29. No production changes; no tests authored or run. Baseline guards unchanged; bot off.

## Classification and candidate recommendation

**Unsupported combination, not absence of ordinary CONSUME Play:** Eat against an actual purchased clone_am is rejected before admission. A restricted playable candidate must disclose this exclusion. A GM ruling cannot report the copy mechanically killed, swallowed, escaped or restored. Retain the early SOURCE_CLONE_BODY_REQUIRED guard. Implementing only high-result death would admit rolls whose other required outcomes cannot execute. A new GM-request bridge would not solve that and is not proposed.

## Concrete source evidence

- services/m3_consume_support.py:170–173: explicit same-copy lifecycle prerequisite.
- engine/m3_clone_am.py: stable purchased copy ref, original actor, Frame, receipt and birth event. r260 Identity-erasure tombstone is not body death. current() has no independent dead/custody model.
- engine/m3_actors.py:520–565: Clone ActorView derives alive from the original, physical location from Frame residency, and hardcodes inside_frame=True. Recording consumption alone cannot make the copy dead or contained. Changing the original affects the wrong person.
- engine/m3_clone_residency.py: same-copy transfer requires paid delivered Frame Swap receipts. It is not a physical custody adapter. Consumption must not forge a Swap or overwrite purchase provenance.
- services/m3_consume_support.py kill(): no clone_am ending branch; unsupported kinds fail SOURCE_BODY_DEATH_REQUIRED.
- Same file _position(), swallow(), escape(): no Clone positioning adapter; _position() falls through for unsupported kinds. Bypassing admission would risk silently unapplied custody.
- Same file forget(): canonical evidence of actual target death is mandatory. Current Clone resolution cannot independently prove this while leaving the original alive.

## Required foundation before admission

1. Resolve authorized printed physical-eligibility rules: can/how can a Frame-resident artificial person be eaten, and is the target its body or carrier? Cast participation alone is not a physical rule.
2. Add source-bound independent lifecycle keyed by immutable Clone ref/purchase/birth: death, custody/location, prior residence, authoritative source/event and idempotency. Preserve history, ownership, privacy and original resources. Never kill/move original by proxy.
3. Make shared resolution/eligibility respect that lifecycle across play admission, casts, Inbox, retention and swaps. Define post-death entitlement, reacquisition/restore and carrier changes during custody from rules, not assumptions.
4. Implement all admitted Eat results: genuine death, custody and escape, interception and permitted alternatives, purchased ontological memory erasure. Use existing transactions; reject before roll when a mandatory result lacks an adapter. No invented Assets or skipped state changes.
5. Genuine-purchase tests: admitted outcomes; wrong actor/copy/controller; replay and stale source; original unaffected; saved/reloaded death/custody; rules-backed restore. Independent rules/code review. Root runs pytest.

Recommendation: explicitly exclude CONSUME Eat → actual Clone AM from the first restricted GM-led test while finishing ordinary supported paths. This is not a claim all other CONSUME branches pass. No runtime GM bridge or completed new workflow is claimed.
