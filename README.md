# HarpyEngine — GIRL FRAME private Discord pilot

M0 is accepted. M1 now implements server setup, persistent owner-bound drafts,
Girl/Frame dropdowns and Discord tags, raw OS-backed 2d6 receipts, a filtered ledger,
OOC safety pauses, retryable public delivery, and local backup/restore/rebuild tools.
Offline acceptance and live verification are tracked in
[reports/M1_ACCEPTANCE.md](reports/M1_ACCEPTANCE.md). The owner confirmed the dice,
receipt/ledger, publication and safety smoke tests. This is not a production
readiness claim.

M2 implementation is ready for owner review: source-backed character creation,
explicit canonical activation, guided pilot Plays, durable human responses and scene
chat locks. New gameplay remains release-gated; independent rules review and human
play-testing are pending. See [the review handoff](docs/M2_REVIEW_HANDOFF.md) and
[M2 evidence](reports/M2_ACCEPTANCE.md). The live policy does not activate characters
or certify rules automatically. M1 raw dice remain a separate test primitive.

M3 is in development and remains **RULES_SUBSET**. The current bounded candidate adds
actual Engage/Harpy extra maneuvers, owned Handler Tag requests and attention notices,
Enforcer acquisition/Snoop/retention workflows, Mockingbird subsets, original-person
Harpy recovery/repossession into an actual Mockingbird and Handler Void, and source-bound Gorgon combat/collateral/world
consequences. The last committed full regression passed **2,200 tests**, with source scope and remaining gates
in [M3 evidence](reports/M3_ACCEPTANCE.md).
Newer development adds supported Virus/Sex/Call, JANUS Core and selected paid
Requisitions including Storage, Leviathan Obsession, source-owned Alpha outcomes
and NPC Orders, bounded AM discovery/Limiters/reset/identity-memory maintenance and backup/revert,
native/grafted Class consumers including Home, five-source Sup growth, Appearance
Matrix, Handler’s Special Girl, Clone AM and source-specific Succubus Orders,
High Rebellion Ritual/backstory effects, actual Rebel group merger/leader opportunity, player-owned stipend retirement,
finite retained Dampener/Kicked Puppy/Untouchable/Martyr/Succubus/Sup/Special Girl/Modular/Matrix/Nightmare/Physiotherapist/Clone, Cute Uniforms actual dressing/Keep/Tag/discipline, Girl Insurance death/Budget/storage effects, direct Location rebuilding/construction, ordinary session/Identity/PR advancement and genuine award/Permission
spending, Supply Drop repair/delivery/expiry, actual NPC departures and Budget Asset removals, and
further Budget meeting/Candidate/Anarchy/cleanup/sabotage/visitor/assassination/fight lifecycles. Focused
normal-workflow evidence is listed in the report; it has not had a new full
regression. Remaining playbooks, Strain branches and world consumers still prevent
whole-M3 acceptance.

Its offline mission flow now
persists private invitations, explicit player responses, dispatch and mission-end
rewards, with required consequences blocking completion. The discipline flow adds
inflictor-owned selectors, delegation, exact-proposal Handler consultation and
atomic effects for twelve Punishment types within supported resources and contexts. DoctorDoctor mission-failure
Obsolescence and Princess mission-end standards now have private review controls
before rewards. Last-Girl-Asset Beating reviews apply Helplessness from confirmed
Frame context. DoctorDoctor scrapping now supports free replacement through player
proposal, an exact Handler package and player confirmation, including required
Court consent and safe Discord-label updates. Severe Punishment and Defeat/recovery
have bounded automated candidates; other playbook and cross-rule follow-ups remain
unfinished. These changes
require a separate, scoped M3 release approval and are not enabled in the running
bot. See [M3 evidence](reports/M3_ACCEPTANCE.md) and
[source coverage](docs/M3_SOURCE_AUDIT.md). Ancillary playbooks are deferred and
disabled by default. M3 world prototypes also provide actual Gorgon NPC/Asset
Attacks, separate Core exposure, and private `/mission position` plus inbox controls
for original body/Frame facts. Unknown legacy positions stay unknown; physical
travel/control and further runtime mechanics remain in development.
The next-refusal Low Rebellion adjustment now uses actual source-bound +2
consumption. Shared Plays under the M3 protocol expose owned root/child recovery
through `/choice resume` and the requests inbox, preserving known dice and prior
answers. Neither feature is deployed to the frozen running M2 bot.
Private random contraband finds now appear in `/mission contraband` and the
requests inbox. The original recipient explicitly accepts or declines the
ordinary Girl Asset. Its details stay out of public sheet views until owned
sharing. This also remains under the M3 development release gate.

The bot is currently **intentionally off** at the owner's request. See the
[M3 completion audit and bounded plan](docs/M3_COMPLETION_AUDIT.md) for implemented
features, unfinished systems and the next delivery units. No new completion
percentage or credit estimate is asserted.
Development follows the [usage-conscious workflow](docs/DEVELOPMENT_WORKFLOW.md):
two implementation agents by default, fixed deliverables, compact handoffs,
focused functional checks and final integrated verification.
Asset Installment and Creature Comforts now have closed automated workflow
checklists, including original owned receipts. Creature Comforts scenes support
actual city locations as well as bases. See [unit evidence](docs/acceptance/m3_units.json);
independent and human acceptance remain pending.

The development social flow now offers exact result dropdowns for Put Someone
Beneath You, original-setter Tag consent, real pin-response Plays and on-scene
Punishment. Temporary removal/restoration preserves actual purchased resources.
Final Frame loss cannot bypass required Defeat. The parallel candidate adds actual Defeat/Dive/Void, original-character careers, Handler creation and paid-scene flows; see [the bounded implementation map](docs/M3_PARALLEL_WORK.md) for exact limits. M3 and unit 2a remain in progress pending remaining cross-rule systems and acceptance.

Read `AGENTS.md` and [the roadmap](docs/PROJECT_ROADMAP.md) before development. The
original planning package remains unchanged in `GIRLFRAME_Discord_Codex_Handoff_v0.2/`;
its historical `planning/` paths refer to that directory.

## Install and check

Use Python **3.12.14**, **uv 0.12.23** and the committed lockfile. On a new machine,
install that Python and `python -m pip install uv==0.12.23`. From the repo root:

```bash
bash tools/install.sh
source .venv/bin/activate
python -m girlframe --help
python -m girlframe health
```

The installer runs `uv --cache-dir .cache/uv sync --locked --all-groups`. It does
not migrate data or start services. Health checks local SQLite, not live Discord
readiness. `.env` is not auto-loaded. `GIRLFRAME_DATABASE_URL` defaults to
`sqlite:///./var/girlframe.db`; only plain local SQLite URLs are supported. Run
from the repository root. Keep databases, backups and policy under ignored `var/`
or outside Git. Never delete a populated database to refresh the environment.

Before upgrading an existing database, make a new private backup, then migrate:

```bash
python -m girlframe db backup --dest var/backups/before-0014.db
python -m alembic upgrade head
python -m alembic check
```

For a fresh database, skip backup and run migration. Startup refuses missing schema
and never migrates automatically. Migration `0003` adds the ledger and captures the
current revision of older drafts as a private baseline; earlier overwritten draft
revisions cannot be recovered. Existing campaigns, channels, roles and drafts are
preserved. Migration `0004` adds private append-only creation progress without
rewriting existing records. Migration `0005` adds immutable private Bond proposals. `0006` adds Handler setup
history and nullable Mentor-nomination provenance for proposals. `0007` adds
private immutable Pair Asset allocations. `0008` adds immutable private Court and
Mentor-callsign setup requests. `0009` adds immutable private assembled review sheets.
`0010` adds immutable party-private Princess/Vatgrown chooser requests, including
Handlers without Pilot profiles. `0011` adds canonical M2 state/history, scenes,
actions, receipts, human decisions, orders, locks and delivery. Existing records
are preserved; migration creates no active character or fictional effect.
`0012` adds private missions and append-only mission/required-work histories. It
preserves existing records and does not approve or enable M3 gameplay. Upgrade a
live installation only as part of a reviewed deployment with its matching code;
the existing frozen bot continues on `0011` during M3 development.
`0013` adds durable Off-Duty periods and append-only period history. Required work
initially belongs to one real mission or Off-Duty period; existing mission records
are preserved. Development controls support Strain/Off-Duty preparation and owned
credit declarations, with no generic resolver for pending Strain effects. These
remain under the M3 release gate and are not deployed to the running bot.
`0014` indexes actual historical scene binds and adds scene/campaign contexts for
required work. Each work history keeps exactly one original context. Rebinding a
channel preserves historical scene identities; unresolved scene work and known
recoverable rolls prevent closing their scene. Upgrade preserves existing work and
does not invent missing scene evidence. Downgrade refuses to discard new scoped
work. This development migration is not applied to the frozen running bot.
`alembic downgrade base` destroys application tables: use only on
throwaway test databases. Never downgrade real campaign data to roll back code.

## Discord application and startup

This Gateway pilot activates **one configured guild per process**, with no global
commands. Install the application with `bot` and `applications.commands` scopes.
Supply the raw bot token only through secure environment variable **`DiscordBot`**.
Never put it in policy, source, commands or logs. The application public key is not
used by Gateway mode; do not configure a competing HTTP interactions endpoint.

View Channels and Send Messages support commands and explicit ledger delivery.
Setup additionally needs Manage Channels. Character tags need Manage Roles and
Manage Nicknames, with the bot's role above label roles and members it should
rename. Read Message History is optional for bounded delivery reconciliation in
the managed ledger. No Administrator bot permission or privileged intents are
required. Changing portal default install permissions does not update existing
server role grants automatically.

For the owner's private test guild, create the synthetic policy once:

```bash
python tools/setup_discord_dev.py \
  --application-id 1566951910601269268 \
  --guild-id 1566954229535608913 \
  --approve-admin-status
python -m girlframe start --config var/discord-dev/policy.json --check
bash tools/run_discord_dev.sh
```

Setup refuses an existing destination; retain and reuse the policy. Its sandbox
is a synthetic **read-only engine-status fixture**, not a runnable game engine.
Policy examples are in `config/discord-policy.example.json`. The offline `--check`
validates policy/sandbox only, not schema, credentials or live guild access.

Actual startup checks the authenticated application and guild, then synchronizes
14 top-level commands/groups in that guild only. The currently running frozen
pre-M3 release retains 13. Reconnect does not resync commands
or duplicate workers. Responses are ephemeral, with mentions disabled. Only an
explicit confirmed setup posts onboarding controls; raw rolls publish by default unless `publish:false`; approved M2 Plays post minimal scene controls and receipts. SDK DEBUG logging must stay disabled because it can
include interaction credentials. HTTP/Gateway use the inherited HTTPS proxy and
verified TLS. SIGTERM and Ctrl-C close the bot.

To keep ongoing source edits separate from the live process, an operator may copy
the tested `src/` into a private ignored release directory and set
`GIRLFRAME_RUNTIME_SOURCE` to that copy of `src/` when running the startup script.
The directory must contain the tested `girlframe` package. Keep policy/data in their
existing locations; do not copy private state into a public release. This freezes
code for that process, without making hosting continuous.
For M3-capable snapshots, also copy the tested `rules/registry.json` beside `src/`.
The wrapper binds that snapshot through `GIRLFRAME_RULES_REGISTRY` unless the
operator explicitly supplies another path. An enabled M3 service checks its
registry digest against trusted scoped approval; a missing or changed registry
fails closed. Default-disabled M3 needs neither a registry file nor approval.

Discord presence shows the actual package version: **Starting v0.1.0** while
connecting, **Running v0.1.0** when ready, and **Restarting v0.1.0** during a
controlled SIGTERM restart. A normal graceful close uses **Stopping v0.1.0**.
Reconnect restores the running presence. The version comes from the application,
so future release version changes update presence automatically. Presence reports
process lifecycle, not campaign readiness or rules certification. It includes no
campaign state or private character details.

Before diagnosing a stopped bot or launching another copy, run
`python tools/check_bot_process.py --expect-one`. It recognizes the supported
launcher including Python's `-u` option, prints only process count/PIDs and changes
nothing. Check the existing execution session and Discord readiness as well;
process count alone does not prove a working Gateway connection.

After disconnection Discord controls the offline indicator. A stopped/crashed bot
cannot publish an offline activity message; abrupt failures can take a heartbeat
timeout to appear offline. Presence updates are best effort and cannot prevent a
clean shutdown. No extra privileged presence intent is required to publish the
bot's own presence.

A process in a development session is temporary hosting and must be restarted after
environment restoration. This work does not publish environment configuration.
HTTP 404 / Discord 10004 at startup means the application cannot access the guild:
check installation and guild ID. Errors omit raw provider bodies and private paths.

## Commands and player flow

Campaign interpretations, their authority, remaining clarity questions and how to
change them are recorded in [the rulings register](docs/CAMPAIGN_RULINGS.md).
The owner delegates future ambiguous-rule recommendations; this does not approve
unimplemented mechanics, player responses or an M3 release.

| Command | Access and behavior |
|---|---|
| `/play` | Owner-bound Play/resource selectors, trigger details, Confirm & Roll; release approval required |
| `/choice resume`, `/choice show` | Own durable responses; permitted saved action/receipt |
| `/mission offer` | Current Handler; private Pilot selector, objective and explicit confirmation; M3 approval required |
| `/mission inbox`, `/mission show` | Invited players/current Handler; saved private offers and progress, with owner-bound actions |
| `/mission discipline` | Assigned inflictor/affected player; native Punishment controls, Handler consultation and owned Paired Heat choices |
| `/mission reactions` | Assigned Handler/affected player; saved DoctorDoctor and Princess mission-end work |
| `/mission replacement` | Player proposal, Handler-defined free package, separate Court recipient response and exact player confirmation |
| `/mission off_duty` | Saved preparation, owned credit declarations and required-work selectors; M3 effects remain gated |
| `/mission strain` | Handler chooses starting scenario, reviews triggers, confirms saved d6 rolls and chooses event columns; unsupported effects stay pending |
| `/mission world`, `/mission map` | Handler setup/management and a player map that omits private world records |
| `/mission repairs` | Actual shortage recovery, private per-Asset Handler quotes and owner-confirmed optional paid repairs |
| `/mission requisitions` | Owned Asset Installment and Creature Comforts purchases, private receipts, actual qualifying Off-Duty opportunities and owned improvement scenes; further Requisitions remain unfinished |
| `/mission regulations` | Private known behavioural rules; informed Handler explicitly records breaches and separate current/next-period discipline |
| `/mission actors`, `/mission cast` | Owned actual-role previews, explicit scene casting and Director selection for Handler-rule responses; actual Handler Girl-rules Keep Your Head uses `/play` |
| `/mission npc`, `/mission npc_bond` | Explicit NPC role claim or owner-confirmed link of a saved starting NPC Bond |
| `/character activate`, `/character state` | Explicit activation/public fields; current private state with paging |
| `/character followthrough`, `/character recover` | Owner follow-through and source-backed moment-alone recovery |
| `/campaign scene_bind`, `scene_join`, `scene_leave`, `scene_close` | Staff-bound scenes, explicit participation and safe close |
| `/campaign order`, `/campaign play_recovery` | Recorded superior orders; confirmed staff recovery |
| `/help` | Configured guild member; private usage |
| `/health` | Explicitly enabled guild administrators; local service/sandbox check |
| `/server setup` | Configured administrator; preview, then caller-bound confirmation |
| `/campaign create name` | Configured administrator; initialize once without resetting data |
| `/campaign join` | Explicit self-enrollment as a player |
| `/campaign handler [member]` | Configured administrator; review/confirm appointment, or omit member to revoke |
| `/campaign mentor newgirl member` | Appointed Handler; review/confirm a Mentor nomination |
| `/campaign status_setup` | Appointed Handler; select, review and confirm the starting rank order |
| `/campaign creation_rules` | Appointed Handler; review and explicitly confirm starting-resource rulings or leave them unresolved |
| `/campaign setup` | Joined member; saved starting Status, Handler and permitted Mentor information |
| `/campaign status` | Joined member or configured administrator; stored M1 status |
| `/campaign_status` | Stored M1 status alias, retaining the earlier approved audience restriction |
| `/character create`, `/girl create` | Joined player; own dropdown draft wizard |
| `/character build` | Joined owner; private starting Assets, Identities, appearance and Newgirl mission history |
| `/character review` | Joined owner; validation, paged private sheet and explicit immutable review snapshot |
| `/character bond member` | Joined player; privately review and confirm a starting Bond proposal |
| `/character bonds [before]` | Participants only; resume saved proposals and accept/decline/withdraw |
| `/character pair_assets member` | Accepted Pair; choose two starting Girl Assets for that Bonded player |
| `/character court member` | Red Queen pilot; select one external AM role and confirm a private request |
| `/character mentor_callsign member` | Accepted Mentor; propose a Newgirl callsign privately |
| `/character requests` | Private overview and guided review for Bonds, Court, Mentor and Pair coordination |
| `/campaign effective_status member` | Joined participant; compare own setup Status to the selected participant |
| `/character sync` | Retry your saved label roles and nickname |
| `/sheet [member]` | Joined player; own private sheet or another member's public sheet |
| `/roll basic [publish]` | Joined owner with saved draft; raw 2d6, published by default; `publish:false` keeps it private |
| `/roll show receipt` | Own private or campaign-published receipt only |
| `/ledger [before]` | Joined player; permitted events, eight per page |
| `/safety pause` | Joined participant; save their own OOC pause, without a reason |
| `/safety resume` | Clear only your own pause; other pauses continue blocking rolls |

DMs, wrong guilds, nonmember identities and inactive campaign membership are denied
server-side. Admin status never authorizes reading another player's private notes
or private receipts. Ownership comes from authenticated numeric IDs, not names,
Discord tags, slash options or claims in messages. Players cannot select arbitrary
campaigns, files, channels or another roll actor. The bot does not consume passive
roleplay transcripts or interpret edited messages as state changes.

Run `/server setup`, review the layout, and confirm within ten minutes. It creates
two categories, seven text channels, and reusable new-player controls. Public
welcome/directory/mission/ledger channels are read-only to ordinary members. Staff
resources deny @everyone visibility. Backend secrets are never posted in staff
channels. Setup saves resource IDs, resumes known partial results, checks permission
drift and never adopts unrelated same-name channels. An ambiguous create pauses
for operator review to avoid duplicates; no teardown command deletes channels.

In `new-players`, join and choose **Create/Edit draft**. Choose Girl and Frame from
dropdowns; enter callsign and optional private notes, review, then **Save draft**.
Only confirmed saves persist. Stable IDs and revisions survive restart. Stale forms
cannot overwrite newer saves. Unsubmitted forms expire; reopen to continue from the
last saved draft. Persistent entry buttons are restored at startup; slash fallbacks
remain available if the entry message is deleted.

Saving queues the Girl/Frame label roles and callsign nickname. SORROW + Mockingbird
+ JANUS-B requests **MOCKINGBIRD**, **JANUS-B** and **SORROW**. Only app-owned,
permission-free label roles are managed; unrelated roles are preserved. A blocked
Discord update leaves the draft saved and can be retried. Discord forbids renaming
the server owner; that test account must set its own nickname manually. Other
hierarchy and permissions restrictions also apply. JANUS-B is an owner-requested
server label using official JANUS rules, as confirmed by the owner. See
[character tags](docs/CHARACTER_TAGS.md).

After saving the profile, use `/character build` to select two Girl Assets and two
Frame Assets, describe them, and fill in appearance/Frame name. Mockingbird chooses
one selected Girl Asset as Void-altered. Wyvern's Enormous is additional. Bonded's Girl Asset names are selected by the accepted Pair, using
`/character pair_assets member` or **Choose Pair Assets** on an accepted proposal.
The Bonded owner sees the selected names in a disabled selector and supplies their
descriptions through **Asset descriptions**, then **Save progress**. The Pair cannot
read or edit the owner's private draft. Starting
Identities are derived from the official playbook. **Save progress** persists a
partial form; reopen the command after a timeout or restart to continue. Unsaved
edits are temporary. Saving changed Girl/Frame playbooks starts new choices while
retaining earlier private history. Creation details are available through the owner-only builder and review;
`/sheet` shows the M1 profile until explicit activation, then the permitted canonical view; `/character state` pages the owner’s full current resources. Creation review assembles the remaining setup inputs; independently approved activation initializes canonical M2 state.
The **NPC Bonds** button selects one or two playbook NPC roles (exactly two for
Oldgen). Names and written feelings are optional and private. Return and Save
progress to persist; these draft NPCs are not merged into shared world canon.

Use `/character bond member` to choose another player from Discord's member picker,
select a starting playbook prompt and review optional context shared with that
player. Confirm saves a pending proposal. The recipient opens `/character bonds`,
chooses it from a dropdown and accepts or declines. Either participant can withdraw
an accepted setup agreement; a source can cancel a pending proposal. No DM or public
notification is sent. Reopen the command after timeout/restart to resume saved
proposals. Unsubmitted forms expire after ten minutes. Private listings show up to
20 proposals, with a `before` cursor for another page; IDs determine page order.

Most Girl branches propose Personal Bonds; Bonded proposes an Intense Pair Bond.
AM's review explicitly tells the counterpart she is Jailbroken. Newgirl's Mentor must first be nominated with `/campaign mentor` by the appointed
Handler. Her proposal is then restricted to that current Mentor; unassigned or stale
nominations return `UNSUPPORTED_RULE`. Newgirl confirms and the Mentor accepts
using the same private proposal flow. Both profiles must be saved and both
members active. Any profile revision change makes old agreement/proposal data stale;
withdraw or decline it and make a new proposal. Duplicate live outgoing proposals
and duplicate live proposals between the same pair are rejected. Accepted proposals
remain draft setup agreements; NPC mechanics, remaining Mentor duties
and playable activation remain pending. Private context/history stays in the database
and backups, outside public sheets, exports and ledger payloads.

Appoint the Handler explicitly: a configured administrator runs `/campaign handler
member`, reviews the reset warning and confirms. The member must have joined the
campaign. Omit `member` to revoke. Appointment grants setup authority only; it does
not grant private-sheet access or Discord permissions. Changing the Handler clears
current starting Status and Mentor nominations while retaining immutable history.
An account acting as Handler is excluded from the Pilot roster, even if it has a
saved test draft. No appointment or game assignment happens on bot startup.

The Handler uses `/campaign status_setup` to select every active Pilot with a saved
profile, highest to lowest, then reviews and confirms. First is Ace, last Dog, and
intermediate positions are Wings. Princess must begin Ace. Multiple Princesses or
fewer than two Pilots require review and are blocked; the native selector supports
up to 25 Pilots. Profile/roster changes make the saved order stale. This is starting
setup, without rewards, punishments or in-play Status changes. `/campaign setup`
shows the stored order and staleness, with Mentor nominations visible only to the
Handler and the affected players.

`/campaign mentor newgirl member` nominates a Mentor for a saved Newgirl profile.
It does not write either player's private creation choices. Changing the nomination
creates a new token and stales old proposals even if the same Mentor is nominated
again. Both profiles and the Handler appointment must remain current. Mentor callsign selection is available after mutual Mentor agreement.
`/campaign effective_status member` compares your setup Status with another
participant, including the current accepted Mentor exception. This read-only
comparison performs no orders, Punishments or other game actions.

Pair allocations require a current accepted Intense Pair proposal from the Bonded
player. Only the other participant selects the names. Owner saves check a current
allocation token and record it with descriptions. Changed selections, withdrawn
agreement, inactive membership or changed profiles block stale forms; reopen the
builder to review. Incompatible descriptions are removed from the current view,
while immutable private history is retained. Reused matching names can retain
description text for owner review and explicit saving against the new allocation.

**Frame setup** in `/character build` shows verified starting facts and preserves
the existing form. Save progress persists a schema-versioned baseline with source
PDF pages. JANUS/JANUS-B has a separate unnamed Harpy Core with its four prescribed
starting Tags. DoctorDoctor has eight-box obsolescence capacity; CONSUME has three
starvation levels; Wyvern has fixed Enormous. Red Queen records five AM roles and
the default four-self/one-other split. Unverified starting counters remain explicitly pending; actual starting AM
role/recipient agreement uses the Court request flow below. No Frame Plays, control over
the Core, or mechanical consequences are enabled by these draft facts. Old saved
JSON loads with the new fields absent; reopening derives current source-backed
facts, and only an explicit save appends a new snapshot.

Use `/character review` after saving creation progress. The native section dropdown
shows Validation, Assets, Appearance, Relationships, Girl setup and Frame/resources, with paging
for long descriptions. The report checks the complete current Status roster,
starting-Bond role/depth, source choices, accepted agreements and campaign rulings.
An eligible outgoing proposal records its owner's starting choice. A player can
explicitly select an eligible accepted incoming Personal Bond from the review,
then confirm; mutual Bonds do not require a duplicate reverse proposal. Newgirl and
Bonded retain their own Mentor/Pair requirements. Clear an obsolete explicit choice
from the same dropdown before selecting a fresh agreement.

**Save review snapshot** stores the saved form and current dependencies privately,
even when incomplete, with immutable revision history. It never saves unsaved builder
edits or activates a character. Reopen/Refresh reports whether the latest snapshot
still matches current choices, memberships, roles, roster and rules. Received Court
roles are included on recipients' sheets. Profile/relationship changes preserve old
snapshots and require review. No administrator can read another owner's private
review; no snapshot is posted publicly or sent to AI.

Newgirl's **Prior missions** button, also available as an inbox task, lets its player
choose zero or one prior mission with each current Cadre counterpart (including the
Handler). Discuss those declarations in conversation, then confirm that discussion
and return to Save progress. Edits clear the attestation; roster/profile changes
require updated declarations. The bot sends no declaration or counterpart consent
merely by opening or saving this private form (book PDF 40 / printed 38).

Starting Heat, CONSUME hunger and marked DoctorDoctor boxes are kept separate from
printed facts. The owner approved **0 / Quiet / 0** as this campaign's defaults.
The trusted local policy can record `owner_creation_rulings` with provenance
`owner_approved_campaign_ruling`; the example leaves it null. No Discord user can
set owner provenance. `/campaign creation_rules` offers the appointed Handler an
explicit preview/confirmation of these campaign rulings, or an unresolved override.
No actual resource pool or playable state is initialized by this setup command.
The regular mode has no optional initial Requisition. Selecting the short-game
variant leaves its additional Requisition unsupported and visibly blocks readiness.

**Girl setup** in `/character build` now covers additional mandatory creation
choices: Oldgen selects two maxims; Princess selects its own standard; Vatgrown
selects one or two desires for each chosen starting NPC investor. Custom Princess
standards use an explicit text form. Return and Save progress to persist. Removing
an NPC role clears only that role's incompatible investor choices from the current
form; earlier saved history remains private and immutable.

A bonded Girl and the appointed Handler each choose a separate Princess standard.
The Handler also chooses its own investor desires for Vatgrown. Those choosers open
`/character requests`, filter **Standards, maxims & Investors**, open the appropriate
task, select options and confirm sending them for private owner review. The owner
accepts or declines through the same inbox. Handler authors require appointment
and membership, without a fake Pilot profile. Roles, profile changes, appointment
replacement and relevant Bond withdrawal invalidate old requests. No administrator
can choose in place of the actual actor. The printed text does not require the
three Princess standards to be distinct; no such constraint is invented.

The review includes source-backed Casualty body parts and Bonded's protected
Paired Identity. CHANGELING records draft Psych String anchors for each current
starting Bond and selected NPC role (book PDF 82), without creating shared NPCs or
running control Plays. Review source version 2 adds these facts and choices; old
version-1 snapshots remain readable history and need refreshing for current checks.

The owner additionally approved unmarked Identities/maxims, undamaged Assets/body
parts, Personal NPC Bonds, zero Permissions, no acquired Requisitions and no extra
Tags as campaign initial conditions. Trusted policy records these under
`owner_initial_conditions`; the public example leaves them unresolved. Printed
exceptions, including JANUS's Core Tags and Mockingbird's Void choice, remain.
These facts are review inputs; no gameplay state is initialized automatically.

**Ready for independent rules review** refers to implemented setup checks only.
Playable activation is implemented behind trusted release approval, absent in live policy. The independent
[source/code review packet](docs/M2_RULES_REVIEW_PACKET.md) records the remaining
gates and source gaps; a player's saved review is not that independent certification.

A Red Queen pilot runs `/character court member`, chooses which AM goes to the
other Girl and confirms. The recipient reviews it in `/character requests` and
accepts or declines. Acceptance records exactly that role on the recipient and the
remaining four on the source pilot. These are draft setup assignments, without
marking AMs, granting controls or invoking Court Plays. Only one current external
Court request/allocation is supported per owner. AM transfer during play is deferred.

The accepted Mentor runs `/character mentor_callsign member`, enters the name and
confirms a request. Newgirl reviews and accepts through `/character requests`. The
accepted name is stored for the final sheet; current profile and Discord nickname
remain unchanged until activation. Mentor nomination or relationship changes
invalidate this choice. Mentor effective Status is computed from the current
accepted relationship, overriding the physical starting rank between those two
characters. Stale/cyclic/unavailable comparisons remain unresolved.

`/character requests` opens a private overview with five summaries per page.
Use Pending, Needs you, Waiting or History, filter by request type and select a
request to review its effects and permitted actions. Back returns to the overview;
Previous/Next and Refresh avoid typed IDs or cursors. Counts cover all eligible
records across sources. Starting Bonds, Court and callsign requests share this
inbox; `/character bonds` remains a fallback. It also routes nominated Newgirl
agreements, Mentor callsign choices, Court assignment, Pair Asset names and owner
descriptions to the existing authorized wizards. Downstream requests replace tasks
instead of duplicating them. Bond elevation and other in-play mechanics await their
rule-backed resolvers.

The inbox is private to participants, with no administrator override and no DM or
public notification. Sender and recipient actions differ; stale versions cannot
be accepted. Saved requests survive restart; ephemeral forms expire after ten
minutes. Reopen the command to reconstruct the current queue.
Accepted choices appear in the owner's builder. Save progress captures their
provenance tokens and rejects a form if shared agreement changed while it was open.
Withdrawal or changed profiles removes invalid choices from the current view while
retaining immutable private history. Starting counters, Cadre discussion, other
Mentor duties, complete validation and playable activation remain pending.

The intended `/play` interface uses guided category/Play selectors, legal targets
and resource choices, review, then Confirm & Roll and result-specific choices.
See [Play interface](design/play-picker/README.md). The requested scene-chat lock
is [specified with acceptance cases](docs/work_orders/M2H_PLAY_CHANNEL_LOCK.md),
pending a real Play resolver and durable pending actions. Neither setup requests nor raw dice lock chat. The M2 implementation binds scene locks to confirmed supported Plays; see the review handoff.

A raw roll returns two faces, their sum, timestamp and stable receipt ID. It changes
no character resources. `/roll basic` defaults to `publish:true`, queuing the receipt
to the managed `rolls-and-ledger` channel. Use `publish:false` for a private roll.
Delivery failures retry without rolling again. Existing saved
receipts remain retrievable while paused. `/campaign status` reports the **bot's
stored M1 campaign**, independent of the recovered engine's paused turn counter.

Ordinary metadata and ledger commands have bounded per-user throttles. OOC safety
pause bypasses that throttle and does not lose a race to unrelated revisions.
Resume clears the caller's request only. No fictional penalty or reason is recorded.

## Persistence and recovery

SQLite WAL is the authority for M1 metadata and raw receipts. The recovered engine's
canonical JSON is not imported, synchronized or modified. The schema has principals,
campaign membership, drafts, command inbox, append-only events/snapshots/receipts,
setup resources, managed roles, tag jobs, safety pauses and a transactional outbox.
Numeric Discord IDs remain membership natural keys; principals additionally have
stable UUIDs. See [M1 ledger design](docs/M1_LEDGER.md).

Each raw roll transaction checks membership, expected campaign revision, pause and
own draft before sampling OS randomness. It commits one receipt, two distinct
indexed events, the command outcome and optional outbox together. An identical
interaction retry returns that receipt, including after restart; changed semantic
payload conflicts. Expected revision is a first-execution precondition, not part of
the roll's semantic hash, so refreshed retries still retrieve the original receipt.
A stale new command samples no dice. Failed transactions expose no receipt.

Delivery is **at least once**, not externally exactly once. Durable leases and claim
tokens prevent ordinary concurrent sends and stale acknowledgements. Retries reuse
a nonce and, with Read Message History, reconcile the last 50 posts in the managed
ledger by bot author and receipt marker. Missing history permission, an older post,
or an acknowledgement race can produce duplicate messages. Each shows the same
saved receipt; delivery never creates another roll or game event. Reconciliation
never scans roleplay channels. Discord edits/deletions do not change stored records.

Trusted local maintenance (not player commands):

```bash
python -m girlframe db backup --dest var/backups/pilot-unique.db
python -m girlframe db restore --source var/backups/pilot-unique.db --dest var/restored.db
python -m girlframe db export --config var/discord-dev/policy.json --dest var/public-export.json
python -m girlframe db rebuild --config var/discord-dev/policy.json
python tools/seed_synthetic.py --dest var/offline-synthetic.db
```

Backup uses SQLite's backup API, includes committed WAL data, and verifies integrity
and foreign keys. Backups contain private data and are created mode 0600. Restore
always creates a **new offline file**, refusing any existing destination. Stop the
bot before deliberately switching `GIRLFRAME_DATABASE_URL` to a verified restore;
keep the old database and policy. Restored pending outbox work may retry delivery.
Public export excludes notes, private receipts and actor/membership IDs. It is a
view, not a full restore source. Export and seed also refuse existing destinations.

Rebuild restores current character public/private projections from immutable
versioned snapshots, and appends local-operator audit provenance; it neither rolls
nor changes recorded receipts/events. It does not reconstruct setup IDs, membership,
safety or delivery operational state from text events; use a full backup for those.
The old pre-0003 draft baseline is explicit, not invented historical revisions.
Run backup before repair. Synthetic seed creates a separate fresh offline DB with
fixed fake identity IDs, one draft and one real OS dice test; do not run it as a live
server database.

## Recovered engine reference

The full private engine and PDFs remain outside Git. The reviewed read-only bridge
reads only strict `turn` and `paused` fields from an explicitly selected disposable
sandbox, without importing/executing private scripts. Configure a trusted absolute
`GIRLFRAME_ENGINE_SANDBOX`, then `python -m girlframe engine-status`. The source must
have the noncanonical marker, `scripts/gm.py` and `state/campaign.json`; symlinks,
malformed types and snapshots over 4 MiB are refused. No sandbox is auto-discovered.

The corrected private package was independently checked with `package_probe.py`,
`verify_engine.py --require-full`, `bootstrap_dev.py`, and its runtime `gm.py validate`.
See [engine inventory](docs/ENGINE_SOURCE_INVENTORY.md). That verification is separate
from bot acceptance and does not certify every mechanic. No v1.3.11 implementation
is claimed. Never run a mutating command against its packaged canonical template.

## Validation and limits

```bash
ruff check .
ruff format --check .
mypy
pytest -q
python GIRLFRAME_Discord_Codex_Handoff_v0.2/verification/verify_handoff.py
python tools/check_repository.py
```

Tests use synthetic data and block outbound network. They cover migrations, private
views, IDs, two-campaign isolation, real SQLite concurrency, fixed injected test RNG,
commit/delivery crash points, restart replay, immutable records, backup/restore,
projection rebuild and fake Discord interactions. Production has no seeded RNG
configuration. In this managed shell, pytest needs supported command escalation
for asyncio worker-thread wakeups; its network block stays enabled. CI performs
offline checks, not live Discord tests. Coverage percentage is not measured.

The historical 86-case catalogue is unchanged; current test mappings are additive in
`docs/acceptance/`. Full rules-certified creation and M2 Plays require a separate
source audit and acceptance. Multi-guild self-service, continuous hosting, retention/
erasure workflows and production security remain unfinished. SQLite and in-process
workers are a private single-writer pilot design. Immutable private draft snapshots
are sensitive history; multi-user release needs a retention policy first.

## Rights and private references

Private development grants no open-source license. GIRL FRAME is authored by
Isabelle M. Ruebsaat; the game, official sheets, names and other third-party material
retain their respective rights. This project does not assert affiliation or relicense
them. Dependencies retain their own licenses. Do not commit official PDFs, private
engine archives, campaign saves, real messages or credentials. `.gitignore` is an aid,
not permission to force-add private material.
