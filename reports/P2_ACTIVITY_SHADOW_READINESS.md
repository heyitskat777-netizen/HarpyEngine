# P2 Activity shadow readiness

This milestone lives on `codex/p2-activity-shadow-readiness`, branched from
manual trial candidate `9a0efbc`. The manual trial worktree remains separate.
The rehearsal uses the manifest-verified Activity overlay and disposable data.

## Existing engine paths reused

- Activity input, immutable revisions, native receipt proof, the per-scene review
  cursor, quiet-window eligibility, renewable worker claims and native closeout.
- The Handler's scoped request and deterministic RESPOND or WAIT policy, reviewed
  Handler drafts, role and cast authority, and the native GM outcomes desk.
- Private NPC reaction proposals, original-controller review, source-backed
  knowledge references and the engine timeline.

## Added in this milestone

- A durable campaign opt-in, scene notice anchored to the actual participants and
  individual consent. Campaign opt-out and roster changes require a fresh notice.
  Withdrawal prevents prior intake from reappearing after renewed consent. The
  journal retains immutable history under its existing access controls.
- A native event cursor catches up eligible commits before accepting the next IC
  turn or claiming a batch. Ordinary **Keep Your Head** and **Check Sensors**
  contribute receipt-backed metadata in ledger order. Their private answers stay
  with the native workflow. Other Plays remain on the existing human GM paths.
- A facilitator-only batch review saves the Handler decision, reason and the exact
  scoped scene or closeout facts available for RESPOND. WAIT is silent. Corrections
  supersede old observations, hide stale review details and invalidate affected
  drafts. The capture-time cast limits hearing even when a role joins later under
  the same account. Reviewed batch contents and cursor advancement commit together.
- Simulated NPC delivery uses an explicit dialogue approval and exact recipients.
  It verifies the original controller, audience, consent, source revision and
  shared citations before saving a single hearing receipt. The role-scoped
  timeline and knowledge expose the contribution only to its original authorized
  speaker and listeners. The review and delivery routes apply zero mechanical
  effects. Human reviewers are responsible for the semantic scope of proposed prose.

## Checks and limits

The broad engine selection passed 97 tests. The follow-up authorization selection
passed 18 tests, with overlap. All 19 managed Activity adapter tests and both
Chromium rehearsals passed.

The engine tests cover simultaneous scenes, approved manual closeout, late cast
hearing, OOC exclusion, native order, retries, restart, withdrawn consent, source
correction, private review, and changed delivery permissions. The browser checks
exercise the new opt-in and private review alongside the original manual fixture.
The managed adapter regression uses simulated Discord authentication.

- [Engine evidence](../var/p2-activity-shadow-engine.xml)
- [Authorization evidence](../var/p2-activity-shadow-authorization.xml)
- [Managed Activity adapter evidence](../var/p2-shadow-final-bundle/pytest.xml)
- [Shadow browser evidence](../var/p2-activity-shadow-browser.json)
- [Manual browser evidence](../var/p2-activity-manual-browser.json)

The readiness browser has a facilitator control to review an eligible batch.
NPC audience approval and simulated delivery are available through the Activity
adapter and exercised by engine integration tests. The managed Discord Activity
remains manual. This milestone validates fixture behavior, local permissions and
native effects. Real Discord, provider quality, and automatic delivery remain
outside its scope.

After reviewing this branch, run the existing supervised manual Discord trial on
the patched, OAuth-configured host. A subsequent opt-in shadow trial needs separate
authorization, a verified retention policy, and a designated test campaign.
