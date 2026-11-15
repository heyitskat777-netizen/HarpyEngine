# P1 player testing — first scoped live session

Current live build: `7aefb3de3674fe80cf7b3c951985b3733477b51c`, **v0.1.1**.
The owner-requested two-starting-Bond house rule is enabled. Select the original
playbook Bond plus an accepted Personal second Bond with a different character
in `/character review`. Handler/configured administrator test exemptions use
`/campaign bond_test member:<player> enabled:true|false`, explicit confirmation,
then a fresh saved review. These exemptions waive Bonds only and create no
agreements. Existing active characters remain intact.
[Focused CI43694295895](https://github.com/heyitskat777-netizen/HarpyEngine/actions/runs/43694295895)
passes **66 tests, zero failures/errors/skips**,93.686s, with changed-source static
checks. This is not a new full regression or human acceptance. **Bot is ONLINE**:
one pinned process, running v0.1.1presence,19guild commands including `/start`
and the new Bond-test command. One existing global `/launch` remains unchanged.
Fresh private backup and the sole requested policy change are verified; schema
is unchanged. Operational authority: `var/discord-dev/p1-deployment.json`.
See [the house-rule evidence](../reports/P1_STARTING_BONDS.md).

The following live correction and deployment notes describe earlier releases.

Current live correction is4a7761e:47focused CI cases pass; bot restarted and
gateway/18guild commands verified. Status/review/member selectors show current
Discord nicknames, with stable IDs retained internally. The Handler may also own
a Pilot; its Status/resources and typed Bonds remain separate from Handler
authority. Reopen `/campaign status_setup`, include that Pilot, confirm the full
order, then complete the accepted starting Bond and save a fresh review before
`/character activate`. Previously opened cards should be reopened through their
commands. This patch has focused evidence; the full-regressed native packet below
is the5412ee8baseline. Human outcomes still require a retry.

The current native repair packet has genuine component reviews and passes its
exact final regression: `5412ee8c431cfee63ecbd8b5e4ff2db97b60c601`,
[full CI43657613489](https://github.com/heyitskat777-netizen/HarpyEngine/actions/runs/43657613489),
3,328passed/0failures/errors/skips plus all global/runtime/planning/privacy gates.
Its actual45-table synthetic restore/reopen and private offline policy check pass.
The owner-enabled live scope
is original native Pilot/Core gameplay with explicitly reviewed sources. Broader
all-type acceptance remains pending and is not inferred from this first session.
The bot is ONLINE on the subsequent frozen4a7761e correction. The matching private policy is installed;
backed-up/rehearsed0011→0020migration preserves existing data. Gateway readiness,
running presence and18guild/0global commands are verified. Human tests below
remain **not tested** until actual participants report their results.

Previously verified offline candidate `a36acabd8a4f9abd21b78f054c7f368ab45cef35` passes its complete
3,300-test CI run, global checks and actual synthetic restore/reopen gate.
See [the evidence and review limits](../reports/P1_FINAL_CANDIDATE_20261114.md).
Independent component source review and owner-authorized scoped deployment are
recorded for the first native cohort. Broader all-type review is open. No fixture
approval is installed live. Older pre-live approval instructions below describe
the preparation gate; they are completed for this release and still apply before
expanding its scope.

## First-session checklist — run in order

Use test characters and at least two Pilots on separate accounts. The actual
Handler may own one of those Pilots. Use a nonadministrator for chat-lock checks; Discord administrators
bypass channel permission locks. Complete the campaign/Handler setup prompts.

| Test | Expected live result |
|---|---|
|1. Online/private replies — `/help`, `/health`, `/campaign status` | Bot responds; private replies stay private. `/health` remains administrator-only. |
|2. Draft dropdowns and Discord labels | Create/edit SORROW as Mockingbird/JANUS-B; selected roles/nickname sync, or an explicit hierarchy/permission warning. |
|3. Saved build — `/character build` | Choose Assets/details, save and reopen. Selections persist; another player cannot edit the draft. |
|4. Canonical sheet — `/character review`, `/character activate`, `/character state`, `/sheet` | Complete listed requests, confirm activation, and see actual resources. Only approved public fields appear publicly. |
|5. Real scene setup | Handler sets world/positions; owners confirm facts. Bind the test channel with `/campaign scene_bind`, join with `/campaign scene_join`, select actual roles through `/mission cast`. |
|6. Roll/receipt — `/roll basic`, `/roll show` | One public receipt by default; reopening its ID retains the original dice. |
|7. Guided Flirt/inbox — `/play`, `/character requests`, `/choice resume` | Correct role/target dropdowns; actual owners answer reciprocal questions and their next decisions. Reopening preserves progress; wrong-user controls are denied. |
|8. Chat hold and safety | Leave real Play work pending: ordinary member chat pauses and restores after genuine completion. `/safety pause` blocks new rolls/Plays; `/safety resume` clears that safety pause without clearing unfinished choices. |
|9. Original Core/Battery/Sin — `/mission janus` | Actual invited Core controller accepts setup, contact and owned answers. When a real Bond change reaches/deepens Intense, only the Girl receives the required Void choice; original receipt/costs remain. |
|10. Actual Harpy/Core social Plays — `/play` | Flirt/Beneath use that actual character's resources and decisions. Harpies gain no ordinary Status, controller Pilot resources are not substituted, and required consequences stay pending until genuinely resolved. |

Mark each row passed/failed/not-tested and report the command, expected versus
observed result and receipt/action ID if available. Keep private responses out of
public reports. Do not force live dice to cover every tier; an untriggered branch
is not tested. Core damage/Defeat and restart-with-pending-work can follow the
initial session using the detailed scenarios below.

## Before scheduling the session

- Close each ordinary Girl/Frame source checklist and review every declared boundary.
- Use the exact verified candidate and retained full CI artifacts. Its pagination,
  global static, migrations/privacy and actual restore/reopen checks pass. New
  runtime changes require relevant verification and a new exact candidate; do not
  infer acceptance of a different source revision.
- Obtain independent source/clarity review. Keep RULES_SUBSET and original full-M3
  backlog intact; do not infer rules certification from passing tests.
- Prepare a private test database and restorable backup. Approve the exact test
  policy/candidate and bot restart separately; record the actual running commit.
  Environment publication remains a separate operation.

## Participants and starting state

Use the agreed Discord test server, one actual Handler, a configured human
facilitator and at least two Pilot profiles with separate accounts; the Handler
may also own one of those Pilots. Another member can
check unrelated-user privacy. Use synthetic campaign content. Assign an NPC to a
real consenting controller when a scenario needs one; the Handler, NPC, facilitator
and player remain distinct fictional/authorization roles even if a human fills
more than one permitted role. No AI/model credentials are needed.

Begin with accepted character reviews, canonical activation and known physical
positions. Keep evidence to scenario IDs, source/receipt IDs, expected versus
observed behavior and the running commit; do not publish private campaign text.

## Session checks

| Scenario | Expected evidence |
|---|---|
| Character creation and reopening | Dropdown choices, actual rule resources, owned coordination and usable saved sheet persist across reopen/restart. Cosmetic nickname/roles match the agreed character. |
| Requests inbox and ownership | Pending work opens the correct native workflow, shows its next actual decision owner and retains earlier choices. A different user cannot answer or read private fields. |
| Roll, public receipt and scene pause | Actual cost/receipt applies once; the public roll appears by default. Chat pauses for required choices and restores after real completion without losing unrelated permissions. OOC safety remains available. |
| Ordinary Girl and Frame play | For each selected type, follow its matrix/source checklist through one ordinary owned outcome and its immediate consequences. Rotate types across sessions as needed; do not require every tier or a Girl×Frame Cartesian matrix. JANUS-B uses official JANUS. |
| Coordination and controlled performances | Confirm consent/assignment separately; use the actual performer's resources. Only printed granted actor decisions transfer; Handler, recipient and other players keep their own choices. |
| Body, damage and recovery | Actual body/Frame/component identity, damage and temporary effects survive readback and restart. Resolve any real required work before source completion; no copied resources, invented cure or narration-only clearance. |
| Private memory/contact workflows | Long returned text stays ordered and lossless in bounded pages; controls and private access survive reopening. Completed contact shows saved route and response privately. Unrelated users/public exports reveal neither. |
| NPC treatment and Court roles | Invite the actual NPC/Director controller and obtain their acceptance. Witness only the actual NPC resources; resolve treatment through its original choices. A restored or transferred Court role supplies its real Tag, with no duplicate on retry or stale role after recall. Handler and Director remain separate humans. |
| Borrowed hardware and rescue | Follow an actual loan through donor Frame loss/replacement and Off-Duty; return the original component through its real custody and owner confirmation. Follow actual medical recovery through witnessed Handler discharge; unresolved required work stays visible. |
| Human facilitator and no-provider flow | A genuine supported source resumes through its validated effect and original receipt. An unsupported adapter stays explicitly blocked. Recipient/delivery uncertainty and scoped pause remain visible; no model call is made. |
| Complete campaign loop | Mission → ordinary social/combat play → consequences/recovery/Off-Duty → next mission succeeds with the same saved characters, resources and chronology. |
| Restart and restore | Reopen pending work after an authorized restart; restore the synthetic backup in isolation and compare real source/receipt/history without rerolls, repeat charges or missing choices. |

## Review record

Record each scenario as **passed**, **failed** or **not tested**, with source IDs and
brief reproduction steps. An implementation or privacy failure stays open. An
untested type/branch is not accepted by implication. Fix demonstrated blockers and
repeat the failed scenario plus directly affected behavior; avoid speculative test
matrices. Player feedback, owner acceptance, final rules certification and live
release approval remain separate outcomes.

## Additional pre-live review scenarios

The separate November14 source review found ordinary Flirt and Harpy/Core
inheritance gaps after the green baseline. See
[the active repair/review packet](reviews/P1_PRELIVE_SOURCE_REVIEW_20261114.md).
These scenarios become live-test candidates only after that exact integration
passes its new regression and matching scope approval. They have not been run by
players.

Use the saved SORROW Mockingbird/JANUS-B character only after its own actual review
and activation. A Core has its own fictional identity and consenting human
controller; that controller's separate Pilot supplies neither the Core's resources
nor its Bond endpoint. JANUS-B continues to use official JANUS rules.

| Scenario | Owned actions and acceptance |
|---|---|
| Reciprocal ordinary Flirt | Original actor asks a question; actual target privately answers and optionally asks its own return question. Reopen the original actor's form and verify the saved question. Each owns its reply/unmarks and later recipient-confirmed followthrough. High-tier work stays pending independently. |
| Actual Harpy/Core Flirt | Make the ordinary interaction in both supported directions. Verify actual Core Heat/Identities/Tags, the original Girl's resources and private questions. A required real escape/Handler/owed-Tag consequence must retain the original source and scene pause. Resolving the owed Tag clears only its genuine refusal restriction. |
| Living Battery and Sin of Temptation | Establish the actual reviewed spinal contact, resolve the Battery roll and choose Bond when it genuinely becomes Intense. The affected Girl alone receives the owned Void choice. Choose an actual eligible Asset; preserve its identity/family, original roll and costs. A capped2→2 change from a genuinely fresh contact produces one new onset; replay of the old response does not. Actual full-family Void keeps its threshold pending. |
| Harpy/Core Beneath | Use the actual Harpy/Girl endpoints, choose the printed tier result and resolve the actual recipient's response. Harpies remain outside the ordinary Status system. Any Punishment, damage or required response must use the original actor/source and finish before the held scene releases. |

For each test, an unrelated member should be unable to open private replies or
submit another participant's form. Test ordinary saved-progress reopening; actual
Discord rendering, permissions and player understanding remain human observations.
Do not use automated user accounts to invoke slash commands. Synthetic adapter
checks use simulated transport and do not establish live-server acceptance.

## First native-cohort command guide

The separately approved migration/policy/startup is complete. Use these existing
controls. Record each result as passed, failed or not tested; no row is already
accepted by a human.

1. Each Pilot completes `/character build` and `/character review`, then confirms
   `/character activate`. Inspect `/character state` and the public `/sheet`;
   only the selected public fields should be shared.
2. Staff uses `/mission world` and `/mission position` for the actual shared
   map/body/Frame facts, with each owner and required reviewer confirming them.
   Channel membership does not establish physical position. Staff binds the
   chosen test channel with `/campaign scene_bind`. Participating
   Pilots join using `/campaign scene_join`. Use `/mission cast` for actual owned
   roles; a Core's controller does not lend the Core their separate Pilot sheet.
3. The JANUS owner opens `/mission janus` to register the original Core. Its
   invited controller and required reviewer each complete their own saved step
   through that menu or `/character requests` before using the Core.
4. Use `/play`; when multiple eligible roles are controlled, choose the actual
   character before selecting the Play. Test reciprocal ordinary Flirt, then
   actual Harpy/Core Flirt and Beneath with the agreed applicable resources.
5. Open `/mission janus` for Living Battery only after genuine contact and
   physical facts are established. Resolve each person's own private choices;
   a real Intense Bond change must leave the Girl's Void work pending for her.
6. Reopen `/character requests` or `/choice resume` as the actual next decision
   owner. Check that required work holds ordinary chat, owned responses preserve
   earlier progress, and unrelated users cannot read or submit private fields.
   `/choice show` reads the original action/receipt without another roll.
7. Check `/safety pause` and `/safety resume` independently of ordinary completion.
   Reopen saved work after a separately authorized restart and verify the same
   choices, receipt and resources.

The installed first policy enables `plays`, `playbooks`, `world` and `discipline`
only, with an explicit seven-Play native Risk opt-in. It does **not** enable
mission dispatch, Strain, economy or Off-Duty. The complete campaign-loop and
all-type rows above require their own reviewed scope; they are not passed or
silently included by this initial session. An insufficient applicable menu or
unavailable source should retain its durable guidance/block, never be cleared
through a fabricated outcome. Live dice stay random; use the retained synthetic
tests for deterministic tier coverage instead of changing a real receipt.
