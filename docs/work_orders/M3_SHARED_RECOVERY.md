# M3H — actual shared-Play interruption and response-chain recovery

Status: IMPLEMENTED_SUBSET / automated boundary checks passed. Independent/human
review pending. This extends the actual M3 release protocol to existing shared
Pilot Plays, recorded orders and owned follow-through. It supplies no new rule
outcome or actor response.

An approved shared Play records its actual registry context. Staff abort stores
each original pending root/descendant state, distinct original human choice IDs,
revisions and body hashes, actual receipt evidence and the distinct abort event
in the same transaction. Only the actual root actor resumes the chain after chat
permissions are restored. Each participant retains their own original decisions;
answered decisions remain answered. Resume reacquires the actual original scene
lock without rolling or spending again. Sources, characters, current participants,
memberships, original Handler, policy and saved bodies must still match.

Cancellation is limited to an unanswered unrolled single reservation. A known
descendant makes even a diceless parent non-cancellable. OOC cancellation can
occur during safety pause; resuming waits for resume. No refund is fabricated.
Known interrupted actor, Off-Duty and shared Plays remain blocking after chat
restoration. New Plays and scene/world mutation cannot discard known outcomes.
An unanswered unrolled reservation does not block otherwise safe world changes,
but its owner must resume or cancel it before another Play. Actual original
metadata binding may repair a legacy character identity after chat restoration
without waiving or replaying its known roll. Native `/choice resume` and the
requests inbox expose owner-bound recovery.

Original aborts without captured interruption evidence get no invented prior state
or automatic recovery. Existing actor/period-specific recovery protocols remain
separate and preserve their original evidence. Canonical rebuild does not invent
operational action rows; a private full backup preserves those rows and their
pending decisions. No migration, live restart or deployment is part of this work.

Acceptance: all known result tiers, prior answered and current pending choices,
different-human child responses, actual diceless order parent, no-known-result
cancellation, correct original owners, pause, stale/changed evidence and actors,
policy/membership/campaign isolation, concurrent replay, abort/recovery rollback,
private backup/rebuild and owned native controls. Full source runtime and generic
career/controller recovery remain M3 work.
