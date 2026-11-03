# M1C — dropdown choices and Discord character tags

Owner-authorized extension: Girl and Frame selections use dropdowns, not free-text
playbook fields. Callsign and private notes remain text. Saving the reviewed draft
also requests the selected type/frame roles and callsign as server nickname.

Use a bounded, source-referenced name catalog. MOCKINGBIRD and JANUS-B must create
roles with exactly those names, with nickname SORROW when the human chose SORROW.
JANUS-B is the owner's server label/variant of the official JANUS family; do not
invent independent mechanics or certify full creation through this UI change.

Queue the request in the same database transaction as the draft revision. Retry
on explicit `/character sync` and after restart. Never lose a saved draft because
Discord rejects a cosmetic change. An older acknowledgement cannot clear a newer
revision's job. Only the owner's own saved selection may be synchronized.

Create app-owned roles with zero permissions, no hoist and no mentionability.
Never adopt same-name unrelated roles. Preserve unrelated membership and remove
only superseded app-owned labels. Refuse privileged, managed, renamed or too-high
owned roles. No role reordering or permission grants are authorized.

Manage Roles and Manage Nicknames, plus appropriate bot hierarchy, are prerequisites
for effects. Discord server owners cannot be renamed by bots. Report each partial
outcome accurately; never claim a blocked nickname was changed. Unknown role-create
outcomes require review instead of duplicate retry. Test dropdown tampering, exact
SORROW example, permission failure, role/nickname hierarchy, owner restrictions,
unrelated roles, safe retries, stale revisions and persisted queue behavior.
