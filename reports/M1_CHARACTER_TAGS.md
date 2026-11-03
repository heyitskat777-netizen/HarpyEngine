# M1 dropdown and character-tag acceptance

**Status: PASS automated; live dropdowns and roles verified; owner nickname blocked by Discord as expected.**
**Date:** 2026-11-02. **Branch:** `codex/m1-character-tags`.

## Delivered

Girl and Frame selections now use two private native dropdowns. Existing recognized
choices are preselected; forged/unknown values and another user's selector are
rejected. Continue opens a two-field callsign/private-notes modal, followed by a
save preview explaining the requested Discord effects. Callsign is limited to
32 characters. Backend validation enforces the catalog as well as the UI.

Saving commits the draft and its desired Discord tags atomically. A per-character
revisioned queue survives restart and retries every 30 seconds, with an explicit
self-only `/character sync` retry. Old acknowledgements cannot clear newer jobs.
Completed jobs are not repeatedly reapplied without a new save/sync request.
Private notes never enter the job. The owner's existing character ID is preserved.

The bot creates only app-owned, permission-free, non-hoisted/nonmentionable label
roles, saves their IDs, and assigns the selected Girl/Frame labels. Superseded
owned labels are removed using per-role endpoints; unrelated roles are preserved.
Same-name unrelated roles are not adopted, and renamed/privileged/managed/too-high
owned roles stop for review. Unknown create outcomes do not trigger duplicate
creation. Deleted known roles can be recreated from their saved ownership mapping.

Callsign is requested as the server nickname, not account username. Manage
Nicknames and hierarchy are enforced; server-owner nicknames cannot be changed
by bots. The UI records/reports a terminal owner warning instead of pretending
that nickname changed. Permissions/hierarchy failures preserve the saved draft.

## Source and scope

Catalog names verified from the supplied official rulebook PDF contents page 3.
JANUS begins at PDF page 68 (printed 66). JANUS-B is the owner's requested server
variant/label, not a separate certified official playbook. No stats, legal build
combinations or rules mechanics are inferred. These remain draft sheets.

See [CHARACTER_TAGS.md](../docs/CHARACTER_TAGS.md), the M1C work order and
[acceptance mappings](../docs/acceptance/character_tags.json). Four complete-builder
cases remain NOT_RUN. Original handoff and private engine are unchanged.

## Evidence

Sanitized commands and actual results: [M1_CHARACTER_TAGS_VALIDATION.txt](M1_CHARACTER_TAGS_VALIDATION.txt).

| Check | Actual outcome |
|---|---|
| Full offline suite | **111 passed; 0 failed, 0 skipped, 0 xfailed** |
| Ruff lint / format | Passed; 64 Python files formatted |
| Strict mypy | No issues in 37 application source files |
| Migration | Fresh/repeated head upgrade, check, downgrade tested; live 0002 applied after local backup |
| Catalog and input | Native limits, unknown/forged choices, selector owner and nickname length tested |
| SORROW scenario offline | MOCKINGBIRD + JANUS-B assigned, nickname SORROW set, unrelated roles preserved |
| Edit / retries | Only owned old tags replaced; missing permissions, renamed/privileged/deleted roles, unknown create outcomes and persisted queue covered |
| Revision race | Older completion cannot clear a newer pending draft |
| Worker | One retry worker across repeated READY; cancellation on shutdown tested |
| Live permissions | Manage Channels, Manage Roles and Manage Nicknames ready |
| Live UI | Owner confirmed dropdowns and tags work |
| Live role readback | Two managed label-role IDs present on member; durable job reached terminal state |
| Live nickname readback | Nickname does not match saved callsign; member is server owner and correct terminal warning is stored |
| Ordinary member rename | Positive path tested offline; a separate non-owner live test was not run |
| Packaging | Wheel 41 entries, source distribution 126 entries; catalog/migration included, no private assets |
| Private engine | 120/120 template hashes unchanged |
| Remote CI | Current remote run not yet observed |

The owner initially reported all visible behavior worked. Independent readback
confirmed roles but distinguished the server-owner nickname restriction from a
successful rename. An early readback ran before the save had committed and found
no job; later data contained the new revision, one job and two managed roles.
A terminal queue state with an owner warning means processing is finished, not
that Discord accepted the blocked nickname. No extra permission can override this
owner restriction; the owner must set their own server nickname manually.

## Limits and persistence

Existing old free-text drafts are not silently converted or assigned roles on
migration. Reopen/resave or invoke self-only sync to request tagging. Unknown
labels require a listed choice. Unconfirmed selections/previews expire; saved
choices and pending jobs persist. One configured guild/campaign per process is
still the private-pilot scope. Real policy, database, roster, drafts, backups,
credentials, GM notes and PDFs remain outside Git. The bot is running in this
session and must be restarted after environment restoration.

A bot-owned label role is cosmetic, not authority over a PC or private data.
Original M1 gameplay ledger/outbox/replay and full rules-certified character
creation remain separate unfinished work. No engine state or dice were changed.
No environment configuration was published.

## Changed files

- `AGENTS.md`
- `README.md`
- `docs/CHARACTER_TAGS.md`
- `docs/PROJECT_ROADMAP.md`
- `docs/acceptance/character_tags.json`
- `docs/acceptance/server_onboarding.json`
- `docs/work_orders/M1C_CHARACTER_TAGS.md`
- `migrations/versions/0002_character_discord_tags.py`
- `reports/M1_CHARACTER_TAGS.md`
- `reports/M1_CHARACTER_TAGS_VALIDATION.txt`
- `reports/M1_SERVER_ONBOARDING.md`
- `reports/M1_SERVER_ONBOARDING_VALIDATION.txt`
- `src/girlframe/database/tables.py`
- `src/girlframe/discord_adapter/bot.py`
- `src/girlframe/discord_adapter/character_tags.py`
- `src/girlframe/discord_adapter/onboarding.py`
- `src/girlframe/engine/drafts.py`
- `src/girlframe/engine/playbooks.py`
- `src/girlframe/services/character_tags.py`
- `src/girlframe/services/onboarding.py`
- `tests/test_character_tags.py`
- `tests/test_database.py`
- `tests/test_onboarding.py`
