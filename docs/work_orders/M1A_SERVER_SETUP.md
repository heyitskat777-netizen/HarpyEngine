# M1A — server setup and persistent campaign foundation

Owner-authorized scope: create persistent campaign/guild binding and membership
foundation before further gameplay writes. Preserve existing read-only behavior.

Deliver: migration-backed campaign/membership/command/event tables; `/server setup`
permission preflight and explicit preview; caller/guild-bound expiring confirmation;
saved template/version and category/channel IDs; per-campaign serialization;
resumable partial setup and explicit uncertain-outcome state; onboarding entry
message stored/reused by ID. Do not create resources merely because the bot joins.

Check caller administrator authority server-side and bot permissions both at
preview and apply. Setup must not use generic player inputs as channel paths or
permission overrides. Require Manage Channels, View Channels, Send Messages;
role provisioning is excluded. Default to the layout in PROJECT_ROADMAP.md.

Acceptance: SETUP-01 through SETUP-08 in the additive acceptance registry. Test
permissions, confirmation ownership/expiry, double execution, process restart,
partial creation, unknown outcomes, wrong guild and private channel overwrites.
Never promise exactly-once Discord resource creation across an ambiguous response.

Evidence: actual commands/counts in `reports/M1_SERVER_ONBOARDING.md`. Live apply is
performed only through a server administrator's explicit confirmation. Record
whether the live preview/apply was run or remains unverified. Do not auto-delete
created resources or migrate real campaign state for testing.
