# P2 private Discord Activity trial

The Activity overlay supports campaign setup and explicit Review & Launch in the
existing role-bound path. Campaign creation binds a Discord role and channel.
The appointed Handler can draft a private persona while Pilots build their
characters. Native owners answer shared starting relationship requests. An
existing Pilot with a verified controller can be designated as an NPC pilot for
the opening. This designation leaves the original sheet and decision authority
with its controller. Each cast member receives their assigned opening brief.

The managed Activity runs in manual mode. Session Zero notes are shared table
guidance. The synthetic lab can separately project the approved opening into
scoped Director knowledge after everyone in the scene consents. The live trial
needs the installed Discord Activity, its SDK and server-held OAuth configuration
on a host serving the patched Activity. Use a fresh role-bound trial campaign.
Previously provisioned stores continue to use their stored owner rulings. New
managed trial campaigns record the existing `owned_shared_choices_preserve_existing`
Handler creation interpretation at provisioning.

## Offline evidence

59 focused engine tests, 19 Activity adapter tests and the Chromium rehearsal
passed. The Chromium closeout filed the four approved Handler opening references
and the scoped Handler contribution.

The engine rehearsal opens two native scenes. The Handler receives the approved
briefing and remains unaware of the Pilot's private input and undisclosed report.
An approved report reaches the Handler when the facilitator manually closes the
source scene. The private discovery stays confined to the Pilot. It also checks
wrong-owner and stale-cast rejection, retry, the native closeout and manual mode.

The supplied simulated Discord host exercises role-bound campaign selection,
verified member sessions, a private Handler draft before Pilot activation, and
the launch blocker for an empty cast. The browser rehearsal exercises review,
launch, recipient-specific briefs, the composer, Handler review and delivery,
reconnect, closeout, and consent withdrawal using disposable accounts.

Reproduce the simulated Discord and managed setup checks from the manifest-verified
source bundle. Supply a new output directory under `var/`.

```sh
.venv/bin/python tools/verify_activity_bundle.py \
  --source /workspace/source-handoff-2026-11-16 \
  --output var/activity-trial-check --p2-routes \
  --test test_campaign_switch.py --test test_managed_campaign_opening.py \
  --test test_scene_popup_plays.py --test test_final_handler_workflows.py \
  --test test_mission_lifecycle.py
```

- [Managed Activity test results](../var/p2-activity-trial-final/pytest.xml)
- [Engine test results](../var/p2-activity-trial-engine-final.xml)
- [Browser rehearsal results](../var/p2-activity-trial-browser.json)

## Supervised Discord session

1. Use the patched Activity host with its actual Embedded App SDK and configure
   its Discord Activity URL mapping for the test application. Prepare an existing
   private test channel and a role for the facilitator and intended participants.
2. As server owner, use `/activity-campaign create` with the trial name, role,
   channel and appointed Handler. Verify `/activity-campaign launch` opens that
   campaign. Confirm a participant without the role is denied.
3. Sign in as the Handler and both Pilots. Save the Handler draft, use the
   existing Pilot setup, and join the opening scene as the actual characters.
   Approve any starting relationships using their native owners.
4. In **Campaign setup**, save and review the opening. Give the Handler one fact
   and a Pilot a different fact. Launch and compare all three recipients' briefs.
   Reconnect and confirm the briefs and original draft revisions persist.
5. Play the first decision in manual mode. Verify one owned native Play and its
   result, then resolve the scene through the existing Activity controls. Keep
   any real model trial and observation enablement as a separate follow-up.

The registered Activity create and launch group is independent of HarpyEngine's
legacy command retirement. Verify the managed launch on the live application
before restarting the updated HarpyEngine Gateway worker with command cleanup.
