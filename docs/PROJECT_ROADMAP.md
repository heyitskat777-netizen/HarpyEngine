# Active roadmap additions

These owner-requested additions supplement the original hash-verified handoff;
do not rewrite that historical package or silently drop its original M1 gates.

| Work order | Scope | Position |
|---|---|---|
| M1A_SERVER_SETUP | Persistent guild/campaign binding, permission preflight, preview/confirm channel provisioning, saved resource IDs and recovery | Current |
| M1B_CHARACTER_ONBOARDING | New-player controls, explicit join, resumable owner-bound draft form, persistent public/private sheet projections | Current |
| M2_CHARACTER_BUILDER | Complete source-audited Girl/Frame creation, legal options and derived resources, validation and playable activation | Before claiming rules-usable characters |

The current read-only commands remain available. Original M1 dice/inbox/outbox,
crash recovery, backups and ledger acceptance remain required before M1 is complete
and before mutating the recovered game engine. Setup/character metadata does not
mutate the engine or import the private canonical campaign. M2/M3 rules work must
verify creation against the supplied official PDFs, not an invented schema.

Acceptance cases and their executable-test mappings are maintained in
`docs/acceptance/server_onboarding.json`; future builder cases remain NOT_RUN.

## Provisioned layout v1

`HarpyEngine` category: `welcome`, `new-players`, `character-directory`,
`mission-board`, `scenes`, `rolls-and-ledger`.
`HarpyEngine Staff` category: `staff-review`.

Welcome/directory/mission/ledger are read-only to ordinary members. New-player and
scene channels allow conversation. Staff resources deny @everyone visibility and
explicitly permit the bot; Discord administrators retain platform-level access.
Backend character secrets never rely on channel privacy and are not posted there.
Mission/scene/ledger channels are reserved surfaces, not implemented gameplay.

Use `/server setup` to preflight and preview, then a caller-bound confirmation to
apply. No resources are created on joining a server or during startup. No roles
are created, no Administrator bot permission is required, and unrelated channels
are neither adopted by name nor overwritten. Manage Channels is required to apply.
The private pilot activates only its explicitly configured guild. A later
multi-guild deployment extension must add trusted per-guild activation before
claiming this command becomes available automatically on arbitrary server joins.
Discord creates and database commits are not atomic: an unknown API outcome pauses
that resource for review, rather than claiming exactly-once creation or duplicating
it on retry. Known completed resources resume from saved IDs.
