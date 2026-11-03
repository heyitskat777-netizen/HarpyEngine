# Dropdown catalog and Discord character tags

## Catalog provenance

Girl and Frame playbook names come from the supplied official GIRL FRAME rulebook,
PDF page 3 (contents). The JANUS playbook begins at PDF page 68 (printed page 66).
Only short factual names are stored in `engine/playbooks.py`; no rulebook prose or
mechanics are included. Ten Girl choices and nine official Frame choices fit native
Discord dropdown limits. JANUS-B is an additional owner-requested server variant
label of JANUS, clearly marked in the menu. No JANUS-B-specific rules are inferred.

## Human flow

Create/Edit draft -> Girl dropdown -> Frame dropdown -> Continue -> callsign and
private notes -> private review -> Save draft. Existing recognized choices are
preselected. Unknown older free-text labels must be replaced by a listed choice;
old data is not silently deleted. Callsign is limited to Discord's 32-character
nickname limit. Selection and confirmation remain owner/guild-bound.

Saving explicitly requests cosmetic label roles plus the callsign as server
nickname. For SORROW / Mockingbird / JANUS-B the desired roles are MOCKINGBIRD and
JANUS-B, with nickname SORROW. Backend identifiers and ownership remain Discord IDs,
not nicknames. Selecting a playbook name is not complete official character creation.

## Persistence and safety

Migration 0002 adds owned-role mappings and a per-character desired-revision queue.
Save and enqueue commit together. Private notes never enter queue payloads. The
process retries pending jobs every 30 seconds and `/character sync` requests a
retry for the caller's own saved character. Completed jobs are not reapplied
unless a new save or explicit sync requests it. Old revisions cannot acknowledge
new jobs. No messages are posted proactively by the retry worker.

The bot creates only allowlisted label roles with zero permissions, hoist false
and mentionable false. Role IDs are saved; same-name unrelated roles are ignored.
Assignment/removal uses atomic per-role endpoints rather than replacing the
member's whole role list. Only superseded owned labels are removed. Renamed,
privileged or too-high owned roles stop for administrator review. Deleted known
roles may be recreated; ambiguous create responses are not automatically retried.

Manage Roles and Manage Nicknames are required for changes, and the bot's role
must be high enough. No automatic role reordering is attempted. Server owners
cannot be renamed by bots, even with Administrator permission; that is reported
as a terminal platform restriction, not a successful nickname change. A hierarchy
or permission failure leaves a retryable job and preserves the saved draft.

The private engine is never mutated. Roles are cosmetic metadata, not authority
to control another PC, access private notes or activate official game mechanics.
Existing drafts have no retroactive job merely because the schema is upgraded:
the owner must save again or invoke `/character sync` to request these changes.
