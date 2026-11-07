# Active roadmap additions

Current local checkpoint adds **Reign of Terror's actual NPC execution and three
supported effect consumers**, plus **another native Pilot as Just Code operator**
with source-scoped Orders and actual damage/owned response. Focused evidence is in
[the M3 report](../reports/M3_ACCEPTANCE.md). Native-PC Execution claims and real Secretary scene
statement delivery are next; other required systems and final review remain open.
Bot off; RULES_SUBSET. Older dated additions below are historical checkpoints.

These owner-requested additions supplement the original hash-verified handoff;
do not rewrite that historical package or silently drop its original M1 gates.

| Work order | Scope | Position |
|---|---|---|
| M1A_SERVER_SETUP | Persistent guild/campaign binding, permission preflight, preview/confirm channel provisioning, saved resource IDs and recovery | Current |
| M1B_CHARACTER_ONBOARDING | New-player controls, explicit join, resumable owner-bound draft form, persistent public/private sheet projections | Current |
| M1C_CHARACTER_TAGS | Girl/Frame dropdowns, safe owned label roles, callsign nickname and durable retry | Current |
| M1D_ENGINE_LEDGER | Immutable raw dice receipts, filtered ledger, safety, durable delivery, backup/restore and snapshot rebuild | Implemented; live human smoke owner-confirmed |
| M2A_STARTING_CHOICES | Source-backed Identities, starting Assets and appearance, private saved progress | Implemented first M2 step; human smoke pending |
| M2B_PLAYBOOK_DETAILS | Vatgrown DNA basis; Prince fanbase demographics, demands, rejections and custom options | Implemented; owner deferred live smoke |
| M2C_BOND_PROPOSALS | Private proposals, participant agreement/withdrawal and durable resume; Newgirl deferred to Handler workflow | Implemented; two-user human smoke pending |
| M2D_HANDLER_NPC_SETUP | Explicit Handler appointment, starting Status, Mentor nominations and saved private NPC Bond choices | Implemented; live human smoke pending |
| M2E_PAIR_FRAME_SETUP | Pair-only starting Asset names, owner-only descriptions and source-backed Frame baselines | Implemented; live human smoke pending, counters/Court assignment pending |
| M2F_COURT_MENTOR_CHOICES | Court role/recipient agreements, Mentor-chosen callsigns and read-only effective Status | Implemented; activation/rename and human smoke pending |
| M2G_GUIDED_INBOX | Five-item private overview, version-bound guided review, source filters and authorized coordination tasks | Implemented; human multiplayer smoke pending |
| M2H_PLAY_CHANNEL_LOCK | Confirmed Play locks only its scene until choices, effects and outcome delivery complete; durable recovery and staff unlock | Implemented offline; independent review and human smoke pending |
| M2I_CREATION_REVIEW | Source-backed validation, Newgirl history, explicit starting Bond choice and immutable private review sheets | Implemented; activation/independent review and human smoke pending |
| M2J_PLAYBOOK_CREATION | Princess three-party standards, Oldgen maxims, Vatgrown investor choices, CHANGELING draft anchors and explicit initial conditions | Implemented; independent review, activation and human smoke pending |
| M2K_GAMEPLAY_COMPLETION | Canonical activation, audited pilot Plays, durable choices and scene locking | Deployed; independent rules review and human acceptance pending |
| M3_RULES_COMPLETION | Full source registry, shared/playbook rules, missions/recovery, Strain and world mechanics | In progress: inventory, core reducers, decision contracts and transactional private mission UI; Punishment/special-reaction resolvers pending; ancillary module deferred |
| M2_CHARACTER_BUILDER | Complete source-audited Girl/Frame creation, legal options and derived resources, validation and playable activation | Before claiming rules-usable characters |

The status commands remain available and now show stored M1 status. Original M1
dice/inbox/outbox, crash recovery, backup and ledger tests are implemented; the owner
confirmed dice/ledger/publication and safety smoke tests. The owner authorized M2 continuation; its first creation step is in progress. Setup/character metadata does not
mutate the engine or import the private canonical campaign. M2/M3 rules work must
verify creation against the supplied official PDFs, not an invented schema.

Acceptance cases and their executable-test mappings are maintained in
`docs/acceptance/server_onboarding.json`, `character_tags.json`, and
`m1_ledger.json`, `m2_starting_choices.json` and `m2_request_inbox.json` and `m2_creation_review.json` and `m2_playbook_creation.json`. Complete-builder cases remain
NOT_RUN until full creation and independent rules review are complete.

## Provisioned layout v1

`HarpyEngine` category: `welcome`, `new-players`, `character-directory`,
`mission-board`, `scenes`, `rolls-and-ledger`.
`HarpyEngine Staff` category: `staff-review`.

Welcome/directory/mission/ledger are read-only to ordinary members. New-player and
scene channels allow conversation. Staff resources deny @everyone visibility and
explicitly permit the bot; Discord administrators retain platform-level access.
Backend character secrets never rely on channel privacy and are not posted there.
Mission/scene channels remain reserved. The ledger supports explicitly published
raw dice tests, without official Play resolution.

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

## Current work — M3

The owner explicitly authorized beginning M3 after the successful M2 migration and
restart. `work_orders/M3_RULES_COMPLETION.md` divides it into M3A–M3H and records the
completion criteria; `acceptance/m3_rules.json` starts every M3/RUL case NOT_RUN.
Start with the exact source inventory and cross-playbook audit, then implement
small tested subsystems. Full agreed coverage and independent/human acceptance
are required before rules-complete certification. Preserve the M2 review gates and
running frozen bot. Stop after M3; M4 and AI remain later milestones.
