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
campaign name/Handler confirmation. Three fixture errors (command-count assumption, missing response mock
and missing actor import) were corrected; affected nodes then passed. A sandboxed
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

Exact published source: `70f9c7a36d16b0c84f35fadeaebf430fe84b9484`.
[Focused CI43686466268](https://github.com/heyitskat777-netizen/HarpyEngine/actions/runs/43686466268)
passes **57 tests/0 failures/errors/skips**,87.428s. Changed-file static, CLI,
rules/planning and repository gates pass. CI scope/JUnit are retained privately.
The exact frozen source also passes the unchanged live-policy offline check and
registers19top-level commands offline.

The authorized restart stopped the earlier4a7761e process and made a fresh0600
consistent backup. New startup failed with Discord LoginFailure; one read-only
`/users/@me` check confirmed **HTTP401**. The new process exited; canonical private
deployment metadata now records `blocked_credentials`, not a running bot. There
was no repeat login, deployment success or live `/start` verification. No state
migration or release-policy change occurred. Existing18guild/0global commands are
the prior registration, not evidence of this patch.

Next: securely replace/save the environment's `DiscordBot` token; verify login
before starting one pinned process, then read back19guild/0global commands.
After startup, use `/start`: create/resume a test draft, confirm one choice and
reopen it; open Campaign setup as the actual Handler/admin; confirm requests are
private and review/activation still require explicit confirmation. Existing
characters should retain their saved choices. Human outcomes remain pending.
