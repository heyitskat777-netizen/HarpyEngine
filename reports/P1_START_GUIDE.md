# Guided campaign and character setup

The owner accepted a single `/start` dashboard to simplify campaign setup and
character creation. This patch preserves the existing forms and rule services.

Implemented:

- Private Campaign setup, Create / Resume character, Pending requests, My sheet
  and enabled Play entry points. Progress is derived from existing saved state.
- Confirmed profile and builder edits save through existing revisioned services;
  opening the guide never joins, provisions, saves, accepts or activates.
- Review snapshots, activation, Handler appointment, Status and other-player
  consent still require their existing explicit actions. Handler and Pilot may
  share an account; activated sheets cannot be reset through the creation guide.
- Existing intake Create/Edit and `/character create` open the guide in the live
  bot. Existing direct commands remain available. Member labels use current
  server nicknames without changing stored IDs or authorization.

Verification before publication: changed-file Ruff check/format (15 Python files)
and mypy (12 source files) pass. Focused local checks cover the projection,
guided saves, private native entry, real review/activation, inbox display and
campaign name/Handler confirmation. Two fixture errors (command-count assumption
and missing mock/import) were corrected; affected nodes then passed. A sandboxed
campaign test stalled in asyncio and was stopped; the identical isolated test
passed outside the sandbox in 1.77 seconds. Original logs remain in ignored var.
Two bounded component reviews found no blocking authorization or state issue.

CI explicitly includes the three new modules alongside the existing focused
pre-live selection. This is a UI patch, not a new full P1 regression or human
acceptance. The 3,328-test full result at 5412ee8 remains baseline evidence.

Known limits: some reused child forms do not retain the guide Back button;
reopening `/start` resumes their saved progress. Girl/Frame/history routes open
the existing builder's section buttons. Saved channel metadata is not a fresh
Discord permission audit. No rule scope, release policy or database schema changes.

Live evidence and a short owner check will be added after exact-source focused
CI and the authorized frozen-source restart.
