# Local HarpyEngine Activity lab

## Character Sheets

**Character Sheets** opens the local creation editor and snapshot viewer. Pick a Girl and Frame, then add the starting Assets, descriptions, and playbook choices. A valid creation file can be exported before setup is complete. The editor preserves omitted and null notes on round trip. Choose **Replace or clear engine notes** to include notes in the export. Leaving that field empty explicitly clears existing engine notes on import.

Use **Open a HarpyEngine JSON file** to load a v1 creation draft for editing or a v1 read-only snapshot for viewing. Draft changes stay in the browser tab until exported. Snapshot printing downloads scriptless HTML that can be opened locally and printed or saved as PDF. Owner notes are excluded unless you opt to include them. Public snapshots show the public projection.

Import the draft through the authoritative HarpyEngine application's preview and confirmation flow once that application runs the v0.1.4 transfer commands. The Activity has no import endpoint, and its existing guided campaign onboarding is separate from the file editor. File exchange supplies no campaign consent, resources, or activation.

Choose JANUS in the Frame dropdown before re-exporting an older draft that uses a retired label. Existing campaign ledgers and their registry-bound approvals require a separate upgrade before use with the renamed catalog.

The catalog, schemas, codec, and declarations under `character-sheets/` come from v0.1.4, commit `fe47d7ef0b558a1106f5dc48b25c277aff5f875b`. To regenerate the committed CSP-safe validators with the existing Node dependencies, run `node harpy-activity-lab/character-sheets/build-validators.cjs` from the app directory. Run `node harpy-activity-lab/verify-character-files.cjs <package.zip>` for the focused browser and packaged-parser checks.

The integrated lab uses the engine and registry from the same checkout. It binds
to IPv4 loopback and uses synthetic SQLite data. From a trusted shell you can set
`HARPY_ACTIVITY_ENGINE_ROOT` to deliberately select a different full checkout
and `HARPY_ACTIVITY_RUNTIME_ROOT` to isolate the SDK and saved lab data. The
default runtime directory is `.sites-runtime/harpyengine-mission-lab`. The two
local launch links require separate browser profiles or contexts.

## Run

```sh
uv sync --locked --all-groups
npm ci --prefix harpy-activity-lab
node harpy-activity-lab/build-discord-sdk.cjs
uv run --no-sync python -B harpy-activity-lab/mission_lab.py --campaign mission-offer
```

Open the **Invited pilot** link printed by the server to see the mission. Open **Other pilot** to create a Mockingbird pilot with a JANUS Frame. Choose a callsign, appearances, Assets, a Void-altered Asset, an NPC Bond, and a starting Bond prompt. Accept the starting Bond from the invited account, then check for updates as the recruit, save the activation review, activate, and join **Relay operations**. The lab sets the synthetic Handler and starting Status order. Each account makes its own Bond decisions. The one-account DM mode also runs the Keep Your Head test below.

Reuse the same `--campaign` name to reopen the same saved campaign, or choose a new lowercase name to seed a fresh offer. Keep test launch links local to the machine.

## Verify

```powershell
node 'harpy-activity-lab/verify-mission.cjs'
```

The verifier uses the locked Playwright package. Pass a local Chromium path,
or install its Chromium build with
`npm exec --prefix harpy-activity-lab -- playwright-core install chromium`.
The browser exercises synthetic logins, not live Discord. The explicit
standalone and integration Python suites also run in the workflow's
`full_suite=true` mode with separate results and loopback-only transport.

## P2 assisted local trial

The trial keeps its own synthetic ledger and starts on IPv4 loopback using the
selected engine. For a historical ledger, intentionally select its reviewed
engine before opening it. Do not use the fixture to migrate a live ledger.

From the integrated checkout:

```sh
uv run --no-sync python -B harpy-activity-lab/mission_lab.py --p2-trial rehearsal --port 8799
```

Open the two pilot launch links and the **GM and Handler** link in separate browser profiles. In each profile, open **Training terminal** and give consent using invented dialogue only. Open the same trial name to resume after stopping the local process. Launch links are regenerated at startup and grant access to their named synthetic account.

1. From a pilot account, file a line of dialogue or a specific Play request. For example, `GM, I choose Keep Your Head to hold the calibration needle steady.` To actually roll, use the existing native Play controls in Relay operations and enter the exact same line.
2. From the facilitator account, use **Open private GM desk** to see requests and engine-proved outcome sources. Bind the original request to the native action once both exist. For Keep, provide the typed task frame in the private GM desk and file the proposed judgment for the original owner's review. Use the source packet and [engine player-test guide](../docs/P2_PLAYER_TEST_GUIDE.md) for the proposal format.
3. The assigned account opens **Review my assigned proposal** and explicitly confirms the intended effects. Use the normal Activity controls for other native choices. An approved GM readback appears only where the viewer can inspect the original action. **Review retained references** assigns source-backed knowledge to specific roles or retires it from prompts.
4. Test **Safety pause**, reopen the trial, and compare what each account can see. Record the Play or proposal ID and any missing or excessive intervention, unexpected disclosure, confusing choice, or lost state.

Run `node harpy-activity-lab/verify-mission.cjs --director-trial-check` from `app` for automated verification of the three local accounts, consent, private review, restart, and safety pause. The trial uses a deterministic local provider and manual structured proposals. Its participant links are for a facilitator operating locally. Connected Discord P2, live data capture, real-model quality, and human acceptance are tracked separately.

### Private Discord P2 trial

`./start-unattended.ps1 -ValidateOnly -P2Trial rehearsal` checks the saved OAuth secret and the named two-pilot and Handler roster. `./start-unattended.ps1 -P2Trial rehearsal` runs the Discord P2 adapter on `127.0.0.1:8798`. The launcher uses the existing OAuth configuration. It skips the command listener and the ordinary campaign registry.

The trial's separate ledger binds the three fictional seats to the original verified Discord accounts. Each named account must pass the existing private-server membership check. The Handler seat also runs the private GM desk for this trial. Reuse the same trial name and roster to recover choices. A changed roster requires a new trial name. Existing Girl or Frame roles continue to apply to the ordinary Activity. The P2 trial uses the explicit named roster.

To run an in-Discord test, the unpublished development Activity's proxy must reach the P2 listener during the session. On launch, each tester signs in under their own Discord account and opens **Training terminal**. Use invented dialogue and the workflow above. A reopening uses a new OAuth session and the same saved seat. The existing Activity's normal origin and campaign listener can be kept separate.

Run `node harpy-activity-lab/verify-mission.cjs --director-discord-check` for the automated Discord iframe and OAuth simulation. It uses the actual Activity server and HarpyEngine store to verify the two pilots, Handler, private GM review, and pending and answered choices across a restart. A live OAuth exchange and Discord client launch need the configured testers to open the unpublished Activity.

## Private Discord build

Discord mode uses the Embedded App SDK to sign users in with `identify` and `guilds.members.read`. The lab verifies test guild membership and reads the user's roles once per sign-in. The Activity session lasts up to one hour or until the Discord OAuth credential expires, whichever comes first. An already open session can retain its prior Discord clearance until it expires. A new sign-in uses the current membership and roles. When accessing campaign records, the Activity still checks the session, current campaign binding, active HarpyEngine membership, and applicable ownership and action rules locally. The required Discord account maps to the invited pilot in the synthetic campaign. An optional second account can test the recruit flow, character creation, and independent Bond consent.

Build the browser SDK from the app directory.

```powershell
npm install --prefix '.sites-runtime/harpyengine-mission-lab/discord-sdk' --no-save --no-package-lock --ignore-scripts '@discord/embedded-app-sdk@2.5.0'
node 'harpy-activity-lab/build-discord-sdk.cjs'
```

In the Discord Developer Portal, open the application that owns the Activity. Under **Activities → Settings**, enable Activities and choose the test platform. Under **OAuth2 → Redirects**, add `https://127.0.0.1` for Embedded App SDK sign-in. The test account needs access to the unpublished Activity as the app owner or a member of the owning developer team. It also needs to belong to the private test server. [Discord Activity setup](https://docs.discord.com/developers/activities/building-an-activity)

Map prefix `/` to the HTTPS tunnel hostname that forwards to `127.0.0.1:8799`. Enter the hostname only and leave Application URL Override off. [Discord local development](https://docs.discord.com/developers/activities/development-guides/local-development)

Set these process environment variables in the shell that starts the lab. Enter the development client secret locally with a masked prompt. Keep it out of the HTML, chat, and command history.

```powershell
$env:GIRLFRAME_ACTIVITY_DISCORD_CLIENT_ID = '<development application ID>'
$env:GIRLFRAME_ACTIVITY_DISCORD_GUILD_ID = '<private test server ID>'
$env:GIRLFRAME_ACTIVITY_DISCORD_INVITED_USER_ID = '<invited test account ID>'
# Optional for the recruit test: $env:GIRLFRAME_ACTIVITY_DISCORD_OTHER_USER_ID = '<second test account ID>'
$discordSecret = Read-Host 'Development Discord client secret' -AsSecureString
$env:GIRLFRAME_ACTIVITY_DISCORD_CLIENT_SECRET = [System.Net.NetworkCredential]::new('', $discordSecret).Password
$engineLab = Resolve-Path '.sites-runtime/harpyengine-mission-lab/HarpyEngine-playtest'
& "$engineLab/.venv/Scripts/python.exe" -B 'harpy-activity-lab/mission_lab.py' --discord --campaign discord-private
```

Launch the Activity from the Discord Developer Activity Shelf in the test server. Sign in with the invited account, accept the offer, close the Activity, and reopen it. It should display **Response saved · Accepted**. If a second account is configured, sign in with it and follow the character setup above. Its mission list should be empty. To confirm the saved event count, run the same Python command with `--audit` in another shell. The non-invited direct-submit and same-key retry checks are scripted below.

```powershell
node 'harpy-activity-lab/verify-mission.cjs' --discord-offline
```

The offline test uses stand-ins for Discord and its SDK handshake, with the real HTTP adapter, HarpyEngine mission service, and SQLite database. It checks both identities, exact retry, changed and stale retries, reopening the iframe, and restart persistence. Launch, OAuth consent, private app visibility, and proxy behavior still need a Discord client test with the development application configured. The lab does not use the live bot or campaign database.

### One-account DM test

For an unpublished Activity already configured to launch from a DM, add `--allow-dm` to the lab command above, or pass `-AllowDm` to the masked-prompt launcher under `.sites-runtime/harpyengine-mission-lab/tools/start-private-lab.ps1`. Use the same `discord-private` campaign name to reopen an existing receipt. DM sign-in still requires the configured account and active membership in the private test server. A launch from another server remains unavailable.

For the one-account launcher, pass `-RememberSettings` to save the test account and encrypt the Client Secret with Windows user encryption in `%LOCALAPPDATA%\HarpyEngineActivityLab`. Future one-account launches for the same application and private server reuse those settings under the same Windows profile. Run the launcher with `-ForgetSavedSettings` to remove that saved entry.

For a private roster, run `start-unattended.ps1 -SaveRoster -FirstPilotId <id> -SecondPilotId <id> -HandlerId <id>` under the same Windows profile. The startup task uses the saved secret and a separate `discord-private-roster` campaign. Each approved pilot starts in native HarpyEngine creation and owns its own sheet under its verified Discord ID. Both pilots save a callsign before proposing a starting Bond. After accepting the proposal, the receiving pilot selects **Use as starting Bond** in the Inbox, and each pilot saves their own activation review. The guided playtest uses MOCKINGBIRD / JANUS.

The appointed Handler signs in to Communications and their assigned scene decisions. The roster campaign uses its own scenes and sheets. The synthetic Battlefield drill belongs to the one-account and fixed-fixture lab modes.

In the private roster Activity, the Handler opens **Battlefield**, files the campaign map if needed, and reviews starting positions. Each pilot selects **Enter Battlefield** and proposes the position of their own activated sheet. The Handler then selects **Start turns**. Turns start in cadre order and persist in the same HarpyEngine campaign ledger as movement and Plays. Each pilot ends their own turn. An unresolved Play keeps its assigned responses available to their owners, including the Handler, and holds the turn.

Before starting turns, the Handler can use **Enemy deployment** to introduce an opposing guard NPC or add an existing visible, mapped NPC or Gorgon they control. Enemy turns follow the pilots and give the Handler **Move enemy** and **End turn**. A pilot in their own occupied Frame can select **Voluntary Core exposure** on their turn. HarpyEngine determines when the exposed Frame becomes an eligible **Go for the Core** target. Mixed casts expose the Activity's actor-aware Plays.

**Campaign Roster** lists bound members even when they are away or have enrollment pending. Online presence reflects a recent check-in from a visible Activity session. Campaign access uses Discord sign-in and the saved tester settings. Invitation codes apply to scenes.

Run `node harpy-activity-lab/verify-mission.cjs --private-battlefield-check --tactical-tier=mid` for the isolated two-pilot and Handler check, including restart recovery.

Run `node harpy-activity-lab/verify-mission.cjs --bound-roster-check` from `app` for the isolated browser and engine scenario. Real Discord testers still need application test access and active membership in the configured test server.

### Bot-managed campaigns

For the existing private HarpyEngine application on Windows, run `./start-campaign-setup.ps1` once from the same Windows profile as the Activity task. Enter the bot token in the masked prompt. The launcher verifies the application, encrypts the token with Windows user protection, and restarts the existing private Activity task. On subsequent starts the task runs the command listener inside the Activity web process. Discord sign-in uses the separately stored OAuth client secret.

The setup bot registers `/activity-campaign create`, `/activity-campaign help`, and `/activity-campaign launch` for the configured guild. Keep the setup bot running to receive these commands. With `create`, the server owner chooses a name, a text or voice channel, an existing Discord role, and optionally a Handler. The Handler defaults to the owner. Assign the bound role to everyone who should open that campaign, including its Handler. A Discord administrator who does not own the server cannot provision a campaign.

The bot initializes a separate HarpyEngine store and saves the channel and role binding in `.sites-runtime/harpyengine-mission-lab/activity-campaigns.sqlite3` by default. From the bound channel, a member with that role can type `/activity-campaign launch` to open HarpyEngine. The Activity uses the roles verified at sign-in to preselect the channel's campaign. Users with access to multiple campaigns can use **Switch campaign** in the header. The existing private test campaign remains available under its existing tester settings.

The Windows Activity task also enables the DM version of `/activity-campaign launch`. The DM command is available in the bot's own DMs and, with Discord User Install configured and the app installed to the user, in other private chats. After sign-in, HarpyEngine opens the only role-bound campaign the member can access or shows **Choose a campaign** when several are available.

Open **Safety** in the Activity header or **Campaign safety** in the enrollment window. It works before character creation and without joining a scene. It pauses the same campaign as the scene safety controls. Anyone signed into that campaign can pause without a reason, and each person can clear only their own pause. If the Activity cannot confirm a pause, stop play and tell the group out of character.

Discord DM notifications use the bot's own Discord requests. Before sending a queued notice, the bot checks that the recipient still holds the campaign role. Checking the Activity Inbox uses the signed-in Activity session.

Run `node harpy-activity-lab/verify-mission.cjs --campaign-switch-check` to switch between two active sheets in separate role-bound campaigns.
Run `node harpy-activity-lab/verify-mission.cjs --campaign-dm-check` to check both DM selection paths with synthetic accounts.

#### Retire the old Discord command menu

Updating the code does not remove commands already registered with Discord. On the host, use the same checked-out Python environment and supply the existing setup bot credential through the host's usual secret loader. Inspect the installed command names without registering or deleting anything.

```text
python harpy-activity-lab/campaign_bot.py --application-id APP_ID --guild-id GUILD_ID --list-commands
```

1. Start the updated Activity listener normally and verify the three guild commands. Confirm Help, launch from the bound channel, and any DM or global launch path the group uses. Check that each of two members can pause and clear their own pause from the Activity header, even without a scene.
2. Verify existing campaign access, pending choices and receipts using the same store. Binding a brand-new campaign is not a migration. Preserve required workflows that are not exposed by the Activity, such as authoritative character file exchange, shelving intake, legacy ledger lookup, and any enabled specialist work. Resolve those paths before removing shortcuts the players still need. Stop any old listener that still syncs the legacy gameplay menu.
3. Set `GIRLFRAME_ACTIVITY_RETIRE_LEGACY_COMMANDS=1` in the managed Activity process for a controlled restart. This is read by the same process that uses `GIRLFRAME_ACTIVITY_SETUP_BOT_TOKEN`. For a standalone command listener, `--retire-legacy-commands` opts into the same behavior. The listener installs the Activity group first, then deletes only the named legacy **guild slash** entries for this application and guild. It does not run a bulk sync, remove global launch, delete context-menu commands, change the campaign database, or turn off gameplay and Inbox workers.
4. Re-run `--list-commands` to check removal and try Help and launch again. Remove the opt-in flag to avoid repeating cleanup on later starts. The flag does not restore removed registrations. If rollback is necessary, the prior host runtime can re-register the previous menu using its original configuration. Keep and reuse the original campaign store.

### Foundation interface

**Scenes** lists rooms by location and offers **My scenes** for rooms you have joined. **Start scene** creates a local staging room. The Relay operations room uses the HarpyEngine scene. Joined pilots can add dialogue or narration to a saved transcript. The Inbox shows mission responses, starting Bond actions, and completed Play updates from any folder.

The transcript opens at the latest message, with the composer and Scene Plays below it. In the composer, `/play` jumps to the current room's Plays and `/play Keep Your Head` opens that Play. Created rooms get a HarpyEngine scene when a member first enters for Plays.

Select a card in **Pilot Profile → Sheet Plays** to choose an eligible scene, including joined created rooms. Use **Enter scene and open Play** to register for Plays in a new ordinary scene. You can keep ordinary scenes open in parallel. A pending Play blocks other Plays in its own scene, and its decisions and receipts stay with that scene. Explicitly cast roles still follow HarpyEngine's cast rules. A Battlefield selection opens the corresponding control in the separate drill when HarpyEngine lists it as ready. The roll still requires submission from the Play form.

The picker shows each scene's current blockers. If a Play needs another pilot, the scene host can open its binding-code invite right from that row. After the other pilot redeems the code and enters the scene for Plays, use **Refresh scene availability**.

**Communications** lists active characters. Direct messages stay in the isolated Activity database and appear in the recipient’s Inbox after a refresh. Pair histories are visible to the two participants, and the Foundation monitoring notice is in-world copy. To enable human Handler replies, set `GIRLFRAME_ACTIVITY_DISCORD_HANDLER_USER_ID` in the lab process to a separate approved Discord account in the test server. That login is scoped to Communications.

The native relay scene offers Keep Your Head, Check Sensors, Engage, and Flirt, with follow-through shown when assigned. Check Sensors and Engage run their base scene procedures. Tactical Engage uses the separate Battlefield drill. Flirt requires another active pilot in the same relay scene. The Test Handler controls stand in for the Handler’s scene choices. Each pilot can set or clear its own safety pause.

Run `verify-mission.cjs --discord-offline --communications-check --relay-plays-check` to verify private messages and the native relay flow with separate test accounts. Add `--relay-tier=high` to exercise the high-roll Tag branch.

**Invite to campaign** and **Invite to room** issue a binding code valid for 24 hours. An eligible test account can redeem it with **Join by binding code**. The first recipient is bound to the code. Discord sign-in and the configured test roster still apply. In a server channel, **Discord invite** opens Discord's own Activity invite dialog. In a DM, copy the binding code to share it manually. [Discord invite behavior](https://docs.discord.com/developers/activities/development-guides/user-actions#open-invite-dialog)

The portrait-free Pilot Profile, Cadre Status, and Frame Status folders link back to the scene or file that opened them. Pilot Profile reads HarpyEngine's current sheet and shows the pilot's Sheet Plays. The owner can see private Identities and playbook changes. Other viewers see public playbook references. A pilot can change the Activity description for its own Frame assets. Damage and Void exposure come from HarpyEngine. Discord sign-in opens a Foundation terminal panel that reports the authorization status.

In the one-account DM lab, **Battlefield** opens a separate HarpyEngine campaign for the relay perimeter drill. **Play** lists currently launchable Plays for the controlled pilot, with a character picker and expandable sheet reference. **Move**, **Engage**, **Check Sensors**, **Keep Your Head**, **All-Out Assault**, and **Go for the Core** use HarpyEngine's movement or Play services.

Use **Expose Core** to let the drill opponent willingly expose its Core through HarpyEngine. The engine determines who can be targeted and which Assets can strike. The test Handler must confirm the opening and reach for an Assault or Core strike. Core rolls use the engine's current Heat options and its intact-Asset penalty. HarpyEngine supplies the defender's counters and damage or final Handler choices. The drill supports Keep Your Head as a nested counter Play.

**Receive Orders** appears for the pilot who has a pending HarpyEngine order. Following it records a response without rolling. Choosing Disobey opens **Disobey Orders** for that same pilot and order. HarpyEngine validates the refusal, rolls it, and supplies the remaining pilot, Handler, and follower choices. **Test Handler · Issue drill order** creates a real order in the isolated drill for the signed-in pilot.

The two-account Discord lab opens a separate shared Battlefield. **Flirt** lists the other eligible pilot in the HarpyEngine scene. Each participant signs in as its own approved Discord account. The target can reopen Battlefield or use **Check for updates** to pick up its choice. The initiating account cannot submit the target's answer, return question, or follow-up choices. The shared lab uses its own drill sheets. To verify the flow offline, use `--discord-offline --flirt-check --tactical-tier=mid` with `verify-mission.cjs`. Low and high tiers can be tested with the same command.

**Put Someone Beneath You** also uses the shared two-account lab. The native outcome determines who chooses effects. The affected pilot supplies its own private Bond or Asset choice, and a pinned pilot can narrate a response or start Keep Your Head. Assigned minor Punishment can be applied by its HarpyEngine owner. Run `--discord-offline --beneath-check --tactical-tier=high` for the pin scenario. Use `--beneath-extra=punish` or `--beneath-extra=lock_tag` for the other high-roll branches.

If the confrontation damages the original pilot's last usable Frame Asset, **Required Defeat** opens in Battlefield for that pilot. HarpyEngine saves the roll using the remaining undamaged Girl Assets and assigns the consequences to that pilot, any optional Tag to the chosen pilot, and a ruinous alternative to the Handler. In the shared lab the synthetic Handler acts through the initiator's existing test controls. Only the affected pilot can accept or decline the saved offer. The original confrontation and Defeat receipts stay in Battlefield history. Run `--discord-offline --beneath-check --tactical-tier=low --defeat-case=mid` to verify the cockpit escape. Use `high`, `low`, or `death` to verify the Tag gift, Handler negotiation, or career archive.

The one-account fixture lets the signed-in tester act as pilot, test Handler, and drill opponent for its tactical tests. Flirt requires the separate two-account fixture. An owned Flirt follow-through appears in **Play**, and HarpyEngine applies the Bond change after the other player confirms it. Required Handler grants support **Brief**, **Escalate**, and **Place an Expectation**. The lab can record concrete ordinary collateral and show saved outcomes under **Past Battlefield Plays**. **Living Battery** appears for a JANUS pilot with an eligible reviewed neural connection.

See the [Activity coverage audit](ACTIVITY-COVERAGE.md) for the remaining basic Plays, Playbook actions, and continuations.

```powershell
node 'harpy-activity-lab/verify-mission.cjs' --discord-offline-dm
```

In **Scenes → Relay operations → Keep your head**, describe what the pilot is trying to endure and click **Roll Keep Your Head** to start the Play. This test uses zero Heat. Pass the Tag window for the pilot and separately for the synthetic Handler. Record the engine’s pilot choice, then enter the test Handler’s ruling. The result shows the original dice, total, traits, and ruling. Reopen the Activity and sign in to see the same result.

The one-account verifier simulates a Discord Activity launch with no server ID. It uses the real HarpyEngine worker and a local delivery adapter. It checks that the original Keep Your Head ruling and roll, mission receipt, moved position, and Battlefield Play results survive reopening and a lab restart. Use `--tactical-tier=low --core-case=low`, `--tactical-tier=high --core-case=mid`, or `--tactical-tier=high --core-case=high` to cover the Core branches. The high Core case seeds Heat only in the offline fixture. Use `--order-check --tactical-tier=low`, `mid`, or `high` to exercise following an order and that tier's refusal.
