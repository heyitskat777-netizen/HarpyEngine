# M2H — confirmed Play locks ordinary scene chat

Owner-requested behavior: a confirmed Play takes priority over new ordinary chat
in its scene channel until its required responses and effects resolve. This is an
explicit extension to the original Play wizard, not enabled by the current setup
inbox. Prerequisites: audited Play resolver, durable pending-action store and a
trusted binding of active scene channels. Never infer a real Play from a raw roll,
setup request, opened menu or untrusted user-provided action/channel ID.

## Lifecycle and scope

- Private preparation does not lock a channel. Confirm revalidates the rule/actor
  and reserves a unique active action for its configured scene channel. Serialize
  competing Plays there; other scene channels and OOC channels remain available.
- Persist desired lock, original relevant permission bits, action provenance and
  recovery state before Discord side effects. Keep roll/spend pending until the
  bot confirms the channel restriction was applied. An absent/ambiguous result
  must be reconciled, not assumed successful. Failure performs no RNG or spend.
- Preserve channel visibility and the bot's ability to post controls/outcomes.
  Restrict ordinary sending, sending in scene threads and creating bypass threads.
  Account for role/member-specific explicit allows; an @everyone deny alone may
  not block other role/member overwrites. Do not change guild-wide role permissions.
- `GuildChannel.set_permissions` requires Manage Roles according to installed
  discord.py documentation; verify actual effective permissions before acquisition.
  Administrators/server owner bypass Discord channel restrictions. The bot cannot
  promise to suppress those accounts, messages already in flight or other bots with
  equivalent permissions. Do not delete other people's messages as a workaround.
- Post a minimal scene-visible Play-in-progress control/status message, with no
  private choice payloads. Buttons/modals and the private inbox carry responses.
  OOC safety must remain reachable through a button and an unlocked channel even
  if a client disables slash entry in the locked chat box. Staff emergency unlock
  must also remain accessible and authenticated.
- Keep the lock through required human choices, canonical resolution and permitted
  outcome delivery. No timeout may fabricate a choice, approve consent or reroll.
  Closing a view does not release the action. Safety pause stops progress and keeps
  controls/OOC access; it never imposes fictional punishment.
- Release on successful completion or an explicitly authorized abort/recovery path.
  Preserve an existing receipt after any abort; never grant a reroll by unlocking.
  Restore only the permission bits the lock owns, merging safely with staff edits.
  Drift that cannot be safely merged goes to staff review, not a whole-overwrite reset.
- Durable leases/outbox/reconciliation and startup recovery must prevent stranded
  locks. Document an administrator's manual recovery path for bot downtime. This
  session's temporary hosting is not continuous hosting and must not be relied on
  for unattended hard locks. No current chat permissions are changed by this plan.

## Acceptance to implement with the Play engine

LOCK-01 Confirmed supported Play locks only its bound scene; preparation, raw dice
and setup requests leave chat open.
LOCK-02 Effective bot permissions checked; failure/ambiguity yields no roll/spend.
LOCK-03 Normal member, role-allow and member-allow cases are restricted; bot controls
still post. Admin bypass is explicitly reported rather than falsely claimed blocked.
LOCK-04 Buttons/modals, private responses, OOC safety and staff unlock remain usable.
LOCK-05 The lock persists across all required choices and releases after resolution
and permitted outcome delivery, including retry/reconciliation.
LOCK-06 Two simultaneous Plays in one scene cannot both acquire/roll; independent
scenes work concurrently.
LOCK-07 Original permission bits are restored, including existing restrictions;
concurrent moderator edits survive or produce an explicit review-required conflict.
LOCK-08 Restart recovers acquiring/held/releasing states and at-least-once deliveries
without duplicate rolls, spends or extra permission grants.
LOCK-09 View timeout/close does not approve a choice or silently release a pending
Play; authorized abort/unlock keeps saved receipt and audit provenance.
LOCK-10 Wrong guild/channel/actor, stale action and forged lock IDs are rejected.
LOCK-11 Thread and existing explicit-role/member-allow bypasses are covered within
Discord's enforceable limits. No visibility or unrelated channel changes occur.
LOCK-12 Human two-player + staff smoke, failure/restart recovery and independent rule
review are required before claiming this works live.

Current status: implemented with offline evidence in `docs/acceptance/m2_gameplay.json`.
LOCK-12 human/independent acceptance remains NOT_RUN. See `docs/M2_REVIEW_HANDOFF.md`.
