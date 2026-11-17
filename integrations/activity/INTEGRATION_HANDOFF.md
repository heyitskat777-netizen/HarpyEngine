# Activity integration return

This integrates the November 16 source bundle into the newer P2 engine. The bundle
is comparison input, not an instruction to operate a campaign. No policy, live
campaign, bot process, Discord application or model provider is changed.

Use the source revision and actual check results in
[the integration report](../../reports/ACTIVITY_ENGINE_INTEGRATION.md).
[The file comparison](../../docs/integration/ACTIVITY_SOURCE_RECONCILIATION.csv)
records reconciliation against the bundle's `5412ee8` base. Current P2 source and
owner policies take precedence over older mirror files. The canonical registry is
unchanged and remains `RULES_SUBSET`.

## Required Activity changes

1. Update the bundled engine to this reviewed source candidate. Do not copy the
   old mirror wholesale over a newer checkout. Preserve the real runtime's policy
   and data; deployment, schema upgrades and private rollout are separate work.
2. Replace the Activity's `mission_desk.py` with
   [the supplied adapter](mission_desk.py). It reads `MissionControlService.view`
   instead of deciding dispatch/closure eligibility from phases and counts. Keep
   existing endpoint authentication and native command routing.
3. Replace the Activity's `player_reset.py` with
   [the compatibility import](player_reset.py). The archive/reset transaction now
   lives in `girlframe.services.player_reset`. Preserve the owner's approval,
   typed exact callsign, character ID, revision and idempotency key.
4. Keep the existing specialist and owned-follow-up forms. They use the merged
   native APIs. Low Memory Extraction exposes no AM installation or linked
   Identity removal. Restoration uses `restoration_options`, a real later event
   and source ID, and the affected controller's optional AM selection.
   `Extraction.am` is nullable; low and NPC memory records must not require an
   AM ID. Existing historical records with an AM retain their saved effects.
5. Render current owner-specific choices and blockers after every command and
   sign-in. Required Feedback, Void resistance, medical/replacement work and
   Punishment retain their original source IDs. A blocked command or narrative
   debrief does not resolve their effects.

In `mission-desk.js`'s `renderMissions`, use `desk.can_offer` to expose the offer
form and display `desk.offer_blocker` / `desk.off_duty_blocker` as text when
applicable. Display each Handler-only `mission.blocked` reason beside its named
transition. Keep using the supplied `mission.actions` list for buttons. These are
presentation changes; command eligibility remains in HarpyEngine. The supplied
Python tests verify the returned controls, not this browser presentation change.

The source-only bundle omits artwork, the browser SDK and installed browser test
dependencies. Python adapter verification uses an empty artwork catalog and an
inert SDK file. It supplies no artwork, browser rendering or live Discord evidence.

## Native mission boundary

```python
from girlframe.services.m3_mission_control import MissionControlService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService

missions = MissionService(store)
controls = MissionControlService(missions).view(verified_viewer)
# controls["offers"]: original mission IDs/revisions, responses, outcome/debrief,
# pending_count. Current Handler additionally receives actions, blocked reasons,
# counts and their owned reactions. Pilot output contains no Handler controls.
# controls["desk"]: Handler-only roster, current period phase and actual
# can_offer / offer_blocker and can_begin_off_duty / off_duty_blocker.

offered = missions.offer(handler, "offer:intent-1", "Survey Relay Nine", (2, 3))
# Each invited Pilot independently calls respond with the current revision.
# missions.respond(pilot, key, id, revision, "accept" | "decline")
# missions.start(handler, key, id, revision)
# missions.end(handler, key, id, revision, True, debrief="Retrieved the relay log")
# missions.complete(handler, key, id, revision)  # only after actual required work
# OffDutyService(missions).begin(handler, key)
```

IDs `2` and `3` are invented test accounts. Construct `GuildViewer` only from the
authenticated server session. Browser role names and IDs confer no authority.
Command arguments retain the existing native signatures and expected revisions.
The controls are read-only guidance; every mutation rechecks authority, source
identity, eligibility and freshness in its transaction. Reuse a key only for an
identical intended operation. Save a new key for changed intent.

The mission debrief is optional, at most 1,200 characters, and saved on the actual
mission. Rewards still come from the native reducer. Pre-reward Princess/Doctor
reviews, compulsory discipline and other required sources block native closure.
Off-Duty still requires Strain, actual scenes, separate acknowledgements, recovery,
review and the native world transition before another dispatch.

## Scope and source proofs

`Approval.activity_specialist_rules` defaults to an omitted empty set. Its typed
allowlist contains only Blank Slate, Psych String generation, Body of Clay, Court
initialization, Memory Extraction and AM Transfer. It requires `rules_subset`,
the exact normalized registry digest, `plays`, recorded rulings, an enabled module
and an implemented/subset source entry. Existing gameplay authorization still
applies. No registry independent-review field is rewritten.

Court initialization does not enable Court marking or Consult. String generation
does not enable String spending. Narrow scoped Clay/Memory acquisitions still
charge actual native Permissions and prove ownership; they grant no general
economy permission. Existing legacy effects remain historical facts.

Blank Slate's mid overstep is limited by the original session, not by a newly
created speech record. Its original speaker pays the real Status consequence.
Legacy Punishment recovery proves the saved applied event, before/after state,
original incarnation and scope before replacing a marker with native owned work.
It cannot invent a favorable outcome, waive work or reroll a receipt.

## Workflow matrix and remaining review

[The matrix](../../docs/integration/ACTIVITY_WORKFLOWS.csv) combines canonical
source contracts and an explicitly curated set of integration branches.
[Curated ports](../../docs/integration/ACTIVITY_READY_PORTS.json) give original
owners, prerequisites, commands, queries, effects, Activity dependencies and named
checks. Each status applies to its particular branch and gate.

[The type port map](../../docs/integration/ACTIVITY_TYPE_PORTS.md) locates native
queries and commands for all ten Girls and nine official Frames, with their
source and ownership dependencies. It is navigation, not whole-type acceptance.

Unreviewed source-index rows intentionally remain `Evidence pending`. Their
candidate files and test references are navigation aids, not proof of a consumer
or all printed branches. Package headings and references do not become invented
mechanics. Full-suite execution does not establish complete rules coverage.
Ordinary branches outside the curated ports still need source-specific Activity
forms and branch/owner/continuation review before the all-type handoff can close.
JANUS-B uses JANUS; Wyvern's chassis is separate from Gorgon Leviathan.

The P2 session/GM/Handler APIs and privacy boundaries remain as documented in
[the P2 handoff](../ai_assistance/INTEGRATION_HANDOFF.md). Fictional Handler context
does not gain GM knowledge; AI proposals cannot supply another controller's answer.
Table outcomes retain the owner-selected GM discretion policy. No model spending
or autonomous live capability is introduced here.

## Reproduce adapter verification

From the engine checkout, with the supplied archive extracted outside Git:

```bash
.venv/bin/python tools/verify_activity_bundle.py \
  --source /path/to/extracted-source-handoff \
  --output var/activity-verification-new
.venv/bin/python tools/build_activity_workflows.py
```

The verifier checks every supplied manifest hash, stages disposable source and
synthetic stores, points the Activity at this engine, and applies only the two
adapter replacements above. It runs the supplied Python tests except artwork.
Keep the output directory new. It saves source hashes and JUnit results.
## Subsequent connected-scene engine increment

The November 17 source adds GM decision-routing metadata/private review, scoped
Handler updates, closed-scene handoff and metadata-only retirement of stale
references. Port the exact contracts in
[the P2 continuation handoff](../ai_assistance/INTEGRATION_HANDOFF.md) and retain
the original native owners and earlier specialist release gates. See
[results and remaining priorities](../../reports/P2_CONNECTED_CAMPAIGN.md).

This is newer than the existing integration ZIP and its 65 supplied adapter-test
results. That package/result remains baseline evidence; it was not rebuilt or
reverified against these additions. No Activity frontend or live backend changed.
