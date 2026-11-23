# Supervised Activity AI trial

Use a separate managed Discord test campaign. In Session Zero, set the Handler
to AI and choose the facilitator in the campaign plan. The group's approval
covers both roles. The appointment takes effect when the Handler opens the
approved introduction. The Handler controller can fill both roles. Another
group member can use the private review desk while playing a Pilot, or choose
a facilitator-only seat.
Select any optional AI Pilot seats in the same plan.

## Assemble the Activity

Use this engine revision and apply the patches in the order listed in
[the assembly tool](../../tools/verify_activity_bundle.py). Copy the Activity
Python adapters and `p2-desk.js` from this directory into the Activity host.
The reviewed AI patch connects the managed campaign registry, authenticated
routes and browser entry point. The signature Plays patch adds lab,
conditioning and punishment forms. The provider setup patch adds a private
connection panel. The Session Zero facilitator patch connects the approved
appointment to the review and provider routes. The facilitator AI setup patch
adds the campaign UUID and provider status to the Activity. Keep the test app's
actual Discord SDK, artwork, protected configuration and existing proxy settings.

To stage and verify the source-only handoff in a disposable directory, run from
the engine checkout.

```sh
.venv/bin/python tools/verify_activity_bundle.py \
  --source /path/to/extracted-source-handoff \
  --output var/reviewed-ai-trial-check \
  --p2-routes --test test_reviewed_ai_trial_activity.py
```

The command assembles a test host with an inert SDK and an empty artwork
catalog. Run the actual Activity from the reconciled, authenticated checkout
using its existing managed campaign start command and the settings below.
The engine uses its existing tables. Apply the existing engine migration
procedure if the rehearsal database is behind the candidate's schema.

## Configure the server

| Variable | Value |
| --- | --- |
| `GIRLFRAME_ACTIVITY_AI_CAMPAIGN` | UUID of the designated managed test campaign. |
| `GIRLFRAME_ACTIVITY_AI_FACILITATOR` | Optional legacy Discord user ID for campaigns with no approved Session Zero facilitator. The facilitator always needs the bound campaign role. |
| `GIRLFRAME_ACTIVITY_HANDLER_MODEL` | OpenAI Responses API model ID available to your project. |
| `OPENAI_API_KEY` | Credential injected into the host process through its secret store. |
| `GIRLFRAME_ACTIVITY_PILOT_MODEL` | Optional model ID for AI Pilot review. |
| `GIRLFRAME_ACTIVITY_DIRECTOR_MODEL` | Optional model ID for private planning and proposals. |
| `GIRLFRAME_ACTIVITY_AI_ATTEMPTS` | Maximum provider attempts per distinct model per process, including timeouts. Defaults to 30. Models with the same ID share the limit. |
| `GIRLFRAME_ACTIVITY_AI_OUTPUT_TOKENS` | Output token limit for each role-model request, from 128 to 8,000. Defaults to 700. |

Open **Facilitator → AI setup** in the selected managed campaign and choose
**Copy campaign UUID**. Before the approved introduction, the campaign's
Handler can see setup if a legacy trial facilitator hasn't been configured.
After the introduction, the appointed facilitator has access. Set the
displayed values in the environment of the process that serves the Activity.
An invalid AI configuration leaves the manual Activity available and writes a
short message to the host log. Configure any spending cap in the provider
project. Use an API model ID available to that project. Codex subagent display
names are session labels.

## Check the provider connection

Sign in to the nominated campaign as the facilitator and expand **Facilitator
→ AI setup**. Opening or refreshing the panel reads only server
status. **Check connection** sends one synthetic request through the configured
model, with an empty game-data packet, and uses one attempt from its shared
process limit. With a real credential, the provider can charge for this check.
The result distinguishes a rejected key, access problem, rate limit, timeout
and unusable response. A successful check verifies the small diagnostic
request. The first consented scene batch verifies actual play.

The panel shows provider-reported input and output tokens for the current
process. Use the provider dashboard for prices and charges. Attempts and totals
reset on restart. A timeout can consume an attempt even when usage is unavailable.
Models with the same ID share the counter and a connection check. Role-model
requests set `store: false`.

## Run the opening scene

1. Open a native scene and join it as the original Handler and Pilot controllers.
   In the Activity, expand **Reviewed AI scenes**, select the scene and open
   **Director work**. Publish the opening with a location, situation and room
   for the Girls' next move.
2. The facilitator enables campaign observation and refreshes the consent
   notice for this scene. Each participant grants consent. Repeat the notice and
   consent step for new scenes or a changed cast. Observation and publication
   can be paused using the existing engine controls.
3. Post eligible dialogue through the reviewed scene's composer. Choose
   **Scene comms** for speech all current recipients may hear, or **Private note**
   for text restricted to its author. The composer shows only the viewer's
   visible timeline and lets them correct their own entries. The ordinary
   Activity chat remains available for unobserved conversation.
4. After a 120-second quiet window, the facilitator chooses **Review eligible
   batch** when the scene is ready. Eligible committed Plays use the existing
   early-review policy. WAIT may leave the scene as it is. A draft remains
   private while the facilitator reviews the original source and audience.
   With a Director model configured, a facilitator in the cast can review a heard cue
   that calls for a separate response-need decision before its batch runs.
5. Approve or reject the draft. The original Handler uses **Deliver Handler
   reply** for approved dialogue, or **Start native Play** for an approved Play
   suggestion. Brief and Get Them Alone carry their wording in their native
   workflow. Confirm lists and choices in the owner-specific controls. Use the
   existing **Handler Plays** and **Off-Duty** panels for shared Play effects
   and later discipline. Pilot contributions wait for their controller.
6. Check the intended Pilot's timeline and work view. Use a third account to
   confirm it cannot see private replies or choices. Withdraw consent and verify
   that pending model review and delivery are blocked. Close out through the
   engine and confirm that only approved facts carry to another scene.

For a manual takeover, disable campaign observation in **Director work** and
use the existing Activity rooms and native Play controls. To disable the host's
provider wiring, remove the campaign nomination and restart the isolated host.
This disables new provider calls. The campaign database retains already saved
records and receipts under its existing backup and retention procedures.

## Campaign export and import

Run the local archive command on the Activity host. Close the Activity and stop
its runner, Discord setup listener and any other campaign writers before
exporting. This keeps the engine and Activity databases at the same checkpoint.
Use a folder with access restricted to the host operator. The archive contains
private records. It preserves the original campaign UUID, Discord role and
channel binding, Session Zero, characters, scenes, pending choices, event
history, audience-scoped knowledge, consent, and the Activity databases if
present. The server's Discord and API credentials are configured separately.

From the Activity's `app` directory on Windows:

```powershell
$py = ".\.sites-runtime\harpyengine-mission-lab\HarpyEngine-playtest\.venv\Scripts\python.exe"
$archive = ".\harpy-activity-lab\activity_campaign_archive.py"
& $py -B $archive list
& $py -B $archive export --campaign "<campaign UUID>" --output "C:\PrivateBackups\campaign.zip"
& $py -B $archive import --archive "C:\PrivateBackups\campaign.zip" --runtime "C:\PrivateBackups\restored-runtime"
```

Create the private backup parent folder beforehand. Import requires a new
runtime directory and checks the archive hashes, SQLite integrity and the
original binding before publishing it. It restores exactly one managed
campaign and prepares its registry and campaign store. Use the matching
Activity build, SDK and existing server credential setup for the restore.
Verify fresh Discord sign-in and original recipient access before using the
restored runtime. Keep the current store until verification is complete.
[Coordinated backup and rollback](../../docs/P2_RELEASE_RECOVERY_RUNBOOK.md).

## Handler signature Plays

| Archetype | Where its signature Play appears |
| --- | --- |
| Advocate | **Director work** opens Get Them Alone in the actual two-person scene. The Girl owns the private answer and Order response. |
| Dogrunner | **Director work** offers Dress Them Down after the scoped admission. The native grant carries the original Girl. |
| Frantic | **Director work** offers Break Down from an eligible scene cue. The Handler confirms the declaration, then resolves any assigned Off-Duty discipline. |
| Mistress | **Signature Play decisions** shows Catch More Flies With Honey after an immediately obeyed Order. The Mistress may pass or offer rewards. The Girl may accept or decline each one. |
| Scientist | **Off-Duty** offers Head to the Lab while a Project start is available. The invited Girl selects her affected Assets. Both original participants confirm attendance before the effects are filed. |
| Insurgent | **Signature Play decisions** shows Rebel Sympathizers after a qualifying witnessed refusal. The Insurgent owns the first observation. A later disclosure belongs to the original Surveilled Girl. |
| Trainer | **Off-Duty** and eligible **Punishment** work offer Conditioning Phrase installation. **Signature Play decisions** handles issued phrases and owned responses, including Hunt’s battle declaration and confirmation. |

The facilitator’s batch review can flag the latter four from eligible native
work. The native cards remain available to their owners when the model stays
silent. The native controls issue Orders, submit responses and confirm effects.

## Optional mission briefing API

Mission briefing generation uses the campaign’s separate
`ai_mission_briefing` policy, with the approved model, processing approval and
reserved spending limits. It also uses the configured canon facilitator for
approval. In **Draft mission briefing**, the Handler queues a draft with
selected known facts, then chooses **Generate briefing**. The facilitator
reviews the saved result before the Handler can offer it to Pilots.
See the [briefing policy and budget](../../docs/work_orders/M5_DRAFT_MISSION_BRIEFING.md).

## Subagent integration

Trusted host code may supply providers to `P2Scene.reviewed_activity(...)`.
Use `ActivityBatchProvider.decide` for the Handler, `ActivityPilotProvider.decide`
for AI Pilots and `DirectorPlanningProvider` for private proposals. Implement
`ScopedActivityPilotProvider.select_audience` to choose listeners before a
Pilot drafts speech. Route requests by original actor identity and serialize
only the engine-provided packet and validated result. An external worker or
subagent can implement these interfaces without game credentials. Retain
continuity in the engine's scoped dossiers and accepted memory. The default
host wires the Responses API, and an operator can supply a trusted provider
implementation when assembling a host with a separate worker.

Offline verification exercises the assembled HTTP authorization with simulated
Discord sign-in and the real engine/provider contracts with an in-process stub.
The installed SDK, Discord embedded login and the chosen paid model still need
an operator-supervised trial.
