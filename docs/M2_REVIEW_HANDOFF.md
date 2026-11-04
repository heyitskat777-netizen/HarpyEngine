# M2 implementation handoff — owner review required

The authorized M2 implementation is complete for the pilot subset below. Stop at
this milestone. Independent rules review and human Discord/mobile acceptance have
not been performed. The owner explicitly deferred play-testing until this handoff.
No M3 or AI is authorized by completion of these automated checks.

## Deployment state

The owner explicitly approved the live migration and bot restart. On 2026-11-04
UTC, a fresh private database/policy backup was created, schema 0011 was applied,
and all 21 prior application tables were verified unchanged before restart. Ten
new empty M2 tables were added; integrity and foreign-key checks passed.

The frozen tested M2 source (`f97dd2c`) reached Discord Gateway READY. Read-only REST
verification confirms 13 guild command groups, including the new Play/choice/scene
commands, and zero global commands. Exactly one bot process is running. The approved
Intense ±2 ruling is now recorded in live policy. Release approval remains null;
no M2 characters, actions or scene locks were created. Independent rules review and
human play-testing are still pending. No environment draft was changed or published.

The earlier automatic deployment rejection was resolved by the owner's subsequent
explicit authorization. Private backups, policy and source snapshots remain outside
Git. Hosting remains temporary to this session.

## Implemented scope

- Explicit, transactional activation from a current, complete, privately saved
  creation review. The owner selects public sheet fields; activation initializes
  canonical Identities, Assets, Heat, Permissions, Status and mutual Bonds. The
  versioned review preserves other starting tracks and playbook facts. Unsupported
  later use of those tracks is not implied by retaining them.
- Canonical state/history is separate from draft metadata and the private recovered
  engine. Activation cannot reset resources. Active profile/build editors are
  blocked. Newgirl's approved name feeds the public projection and cosmetic sync
  without invalidating its own saved setup provenance.
- Guided `/play` for Keep Your Head, Check Sensors, Engage the Enemy, Disobey Orders
  and human-Pilot Flirt. Receive Orders is diceless and requires a recorded order
  from a current superior. The implemented Handler response is Brief Them on the
  Situation. Source pages, tiers, interface contracts and test symbols are in
  `src/girlframe/engine/m2_registry.py`.
- Pre-roll Identity/Heat choices; forced full spend at 5+ Heat; immutable raw
  receipt; post-roll human Tag proposals, one Girl Tag and Status arbitration.
  Personal and Intense Bonds both use ±2 **by the owner's campaign ruling**.
- Exact result counts, owned Assets, human Handler answers, low Disobey refusal
  halt, witnessed Status loss, all three high Flirt branches, real nested response
  Plays, explicit target answers and target-confirmed future Bond improvement.
- Source-linked Princess/Alpha/Oldgen/Wyvern Keep Your Head exceptions, Alpha Dog
  modifier, Newgirl Mentor Tag restrictions/self-marking, and Bonded Paired Heat
  and Tag conversion. Other playbook triggers remain unsupported.
- Persistent owned responses via `/choice resume` and `/character requests`;
  `/choice show`, `/character state`, `/character followthrough`, and explicit
  moment-alone Helpless recovery via `/character recover`.
- Staff-confirmed scene binding; explicit join/leave/close; one root pending Play
  per channel, independent scenes, durable locks before RNG/spend, permission-bit
  snapshots, safe restoration, minimal public controls and outcome delivery.
  `/campaign play_recovery` provides audited abort/retry/restoration.

## Release gate and review

Live `m2_approval` remains null. No real character is activated by startup, migration
or tests. New gameplay returns `M2_REVIEW_PENDING` until a trusted operator records
an independently reviewed release. Discord administrators cannot self-certify it.
Tests supply **synthetic approval only**. A saved player's review is distinct from
release approval.

Review the official PDFs locally alongside the registry, source and tests. Record
reviewer identity, source versions, date, findings and decision. Resolve findings
before setting policy `m2_approval` to `{ruleset, registry_sha256, reviewer,
reference}`. Obtain the digest locally with:

```bash
python -c 'from girlframe.engine.m2_registry import registry_digest; print(registry_digest())'
```

The ruleset is `girlframe-m2-pilot-1`. Any registry change invalidates approval.
Trusted policy separately records `owner_intense_tag_bonus: 2`; source provenance
for starting Heat 0, Quiet hunger and unmarked/undamaged initial conditions remains
unchanged. Never commit live policy, private reviews, PDFs or campaign data.

## Consolidated human acceptance, after review

Use two actual player accounts and the appointed Handler. Begin with the saved
creation workflow: build/save/reopen, agreement inbox, Handler Status, playbook
coordination and current saved reviews. Verify owner privacy and selected public
fields. Explicitly activate both players after the release gate is approved.

Bind a dedicated text scene, have players and Handler join, then exercise all
three tiers of each supported Play as they occur naturally. Do not enable seeded
production dice or reroll saved receipts to force a tier. Offline fixtures cover
exact tiers; human checks cover client behavior and authority.

Check preparation has no chat effect; confirmation locks ordinary text/thread
sending before rolling; dropdowns/modals, private inbox and the Safety button stay
usable. Confirm all required people answer, then delivery and restoration finish.
Check `/character state` and permitted public `/sheet` after effects. Repeat across
mobile and desktop, reopen after a timeout/restart, and confirm no extra roll/spend.

Test missing bot permissions, interrupted delivery, two competing Plays and staff
recovery in disposable test scenes. Verify permission restoration preserves unrelated
staff edits and conflicts stay visibly in review. Ensure OOC `/safety pause` remains
available from an unlocked channel and does not impose a fictional consequence.
Record actual outcomes; these human checks are currently **NOT_RUN**.

## Operator recovery and limits

Temporary session hosting can stop. While the bot is offline, a guild administrator
can manually restore a locked test channel's Send Messages, Send Messages in
Threads, Create Public Threads and Create Private Threads overwrites. The exact
snapshot is private in `m2_locks.body_json`; preserve it and the database. Do not
reset all overwrites or delete campaign data. Once running, use the current root
ID from the scene controls and `/campaign play_recovery` to reconcile; abort
preserves committed receipts and resources. Completed actions cannot be undone by
unlocking. Explicit delivery retry may duplicate a Discord post with the same
receipt, but cannot create another backend roll.

Bot permission changes cannot block administrators/server owner, messages already
in flight, or guarantee instantaneous exclusion of concurrent moderator edits.
Held locks are rechecked by the worker; drift stops new progress for staff review.
No Message Content intent, transcript interpretation or message deletion is used.
Nonce recovery examines only the last 50 messages in explicitly bound scenes;
unknown outcomes require review rather than blind resend.

Unsupported: other Plays, NPC/Gorgon mechanical targets, missions, Off-Duty,
Punishment resolution, optional playbook/Frame triggers, Core/AM control, further
recovery triggers and full published-rule coverage. Pending future punishments are
retained obligations, not silently resolved. Final-Asset defeat branches require
unsupported Defeat/opponent resolution and stop rather than inventing an outcome.
Helpless defensive play is conservatively blocked until implemented recovery.
These boundaries require independent review before broader table use.

Back up before migration/repair. Schema 0011 adds ten M2 tables without rewriting
existing tables. Full backup includes private state and operational locks/outbox.
`db rebuild` also restores the M2 projection from immutable private history; it
never rerolls or invents deleted delivery/membership records. Public export uses
explicit canonical visibility for activated characters. Restore into a new offline
file, never overwrite a populated running database.
