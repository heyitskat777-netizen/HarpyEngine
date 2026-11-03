# M1B — new-player area and persistent draft sheets

Deliver persistent new-player buttons and slash fallbacks: `/campaign join`,
`/character create`, `/sheet`. Join is an authenticated human action, never an
automatic role grant on guild entry. Bind one draft to the campaign/user ID, not
display name. Edit/resume via the same owner-bound private form. Private notes
must remain owner-only even for another server administrator.

Persist drafts transactionally with revision checks, interaction idempotency and
audit events. Same interaction/payload replays the stored result; changed payload
conflicts. Old forms cannot overwrite a newer revision. Confirmed save returns a
stable character ID. Public sheet projections omit notes; Discord messages are
views of the database, not the record. Backend records are referenced by services.

M1 fields are callsign and proposed Girl/Frame playbook labels, plus private notes.
Explicitly label these **draft / rules unverified**. Do not generate numeric game
stats or call these playable official characters. Full creation is a separate
work order. Never use real campaign state or official PDF text as generic fixtures.

Acceptance: CHAR-01 through CHAR-08 in the additive registry. Test restart/resume,
identity and guild isolation, same-name users, stale forms, duplicate requests,
private/public views, admin nonownership and persistent UI routing. Record live
button/modal/sheet tests separately from offline transport tests.
