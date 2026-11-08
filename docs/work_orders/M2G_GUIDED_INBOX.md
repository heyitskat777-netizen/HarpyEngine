# M2G — overview inbox and guided request review

The owner chose the recommendation from `design/request-inbox/`: A overview with
five summaries per page, opening B detail review for one request/task at a time.
Use a native dropdown, effect preview, role-specific actions, Back, filters,
Previous/Next, Refresh and Close. Bind selection to source identity/revision.
Unify starting Bond, Court and callsign requests under `/character requests`.
Derive coordination tasks for nominated Newgirl agreement, Mentor callsign choice,
Red Queen allocation, Pair Asset names and owner descriptions. Reuse existing
service commands/wizards and authority; no new rules, automatic assignment or
mechanical Bond elevation. Future rule-backed choices require their own adapter.

Counts/filtering cover all eligible records across sources, not limited per-source
pages. Only current user's parties/tasks, no administrator private-data override.
No duplicate task when its downstream request is pending/accepted. Explain stale
requests and block acceptance; allow permitted decline/withdraw. Refresh and reopen
reconstruct current data. No background mutations or notifications. Every click
rechecks role, state and expected revisions before delegating existing commands.

Acceptance: mixed-source totals, more than 20 records, categories/scopes, owner-only
controls, sender/recipient actions, stale versions, task dedup and role routing,
private notes, isolation, repeated delivery, refresh/close/restart, fake Discord UI,
five-item overview paging, version-bound selection, review and Back navigation.
Keep native `/play` flow a documented plan; implementing Plays is outside this UI change.
