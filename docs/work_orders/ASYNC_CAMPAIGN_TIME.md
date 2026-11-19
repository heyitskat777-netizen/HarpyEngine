# Offline asynchronous campaign time

The owner authorized a bounded chapter-cut and scene-slot slice on the M3
RULES_SUBSET checkpoint `c4550ecbd89bbf84363537e7bdf763c2177a998f`. It uses
synthetic fixtures under the existing M3 approval policy. The original M0–M7
gates still apply. See the [design Page](https://chatgpt.com/space/page_4c6a6f29ec8081918465a39f8050dfc4).

## Delivery contract

The Handler anchors a synthetic campaign, schedules two independent scenes in
the same afternoon, and previews a cut with an actual required Medical decision.
The existing owner resolves the decision. The Handler takes a fresh preview and
commits once. An independent scene can close without changing the date. A
separately classified debrief can continue after the cut with narration and
audience-scoped notes. Proposed changes to injury, roster, resources or other
mechanics go to the Handler for review through existing rules authority.

| Seam | Reuse |
|---|---|
| Scene identity, attendance and closure | `services/m2_game.py` scene bind/join/close and `services/m3_work.py` source-bound scene context |
| Handler, safety and rules gate | `services/handler_setup.py`, `services/m3_missions.py`, `services/m3_access.py`, `services/m2_game.py` |
| Rules phase | `services/m3_missions.py`, `services/m3_off_duty.py`, `services/m3_off_duty_cycle.py` |
| Decisions and Play receipts | `m3_required_work`, `m2_choices`, `m2_responses`, `m2_actions` and `m2_receipts` |
| Persistence and replay | `services/onboarding.py` serialized writes, private audit events, and the campaign command inbox |
| Projection | An authorized engine service returning the same fields to Discord and Activity integrations |

Timeline records are additive private events. A cut retires the original playable
binding for an explicitly classified debrief only when the normal closing checks
pass and closure would apply zero rules effects. The same historical scene ID
remains open for late narration. No legacy gameplay command can use the retired
binding as a playable scene. Existing scenes without a schedule require explicit
classification before crossing a cut. Protected mechanical facts stay in the
existing rules state.

Test the ordinary cut, coarse overlap, late closure, audience filtering, stale
preview, receipt retry and command rollback. Reuse existing tests for Play
recovery, scene closure and the explicit Off-Duty cycle. Keep mission-minute
timing as the next work order after the core slice is accepted for that follow-on.

## Integration

Use the committed HarpyEngine environment and database at its existing schema
head. The package adds no dependency or schema revision. The base commit matched
GitHub `main` when inspected. Apply the source patch from the package with
`git am <patch-file>` on that base and run the focused tests described in the
acceptance report. When integrating against newer changes, check both affected
scene services and run the same compatibility selection.

Import `CampaignTimeService` from `girlframe.services.campaign_time` and the
request models from `girlframe.scenes.campaign_time`. Construct the service with
the campaign's existing `OnboardingStore`. Resolve an authenticated
`GuildViewer` on the server for every request. Pass the stable delivery key from
the existing command path to every write. Submit the exact prior request when
retrying a delivery.

| API | Contract |
|---|---|
| `initialize(viewer, key, anchor)` | Saves an explicit fictional day, slot and chapter using the checked Handler appointment. Use synthetic campaigns for this slice. |
| `schedule(viewer, key, channel, scene_id, expected_scene_revision, expected_anchor, plan)` | Schedules or revises a real scene binding. Start and end are inclusive. Reservations list intended participants and do not join them. Use the normal join command to confirm participation. The optional plan chapter defaults to the current chapter. |
| `preview_cut(viewer, cut)` and `commit_cut(viewer, key, cut, token)` | The Handler sees dependency IDs and blockers. Reference actual `work`, `choice` or `play_receipt` IDs. Work uses the current resolution event. A Play choice needs its saved response and a completed action. A Play receipt also needs a completed action. Submit the exact target, dependency list and token after explicit confirmation. Refresh on `STALE_CUT`. |
| `record_late(viewer, key, scene_id, expected_cut, submission)` | Actual participants can request review of mechanical or uncertain outcomes. Only the Handler records narration and explicitly grants knowledge to named, joined recipients. Notes and review requests are kept in the private timeline ledger, separate from game-state facts. |
| `close_late(viewer, key, scene_id, expected_cut)` | Ends the narrative continuation using the original cut receipt. Routed reports remain visible to their authorized audience. Use ordinary scene close for a playable scene. |
| `projection(viewer)` | Returns version 1 of the audience-filtered read model. Both clients can consume this method. |

### Projection fields

- `mode` is `legacy` until the anchor is explicitly initialized. In that mode,
  the response contains only `version` and `mode`. In asynchronous mode,
  `anchor` carries `chapter` and `position` with fictional `day` and `slot`.
  `anchor_receipt` identifies the current committed anchor. `slots` holds the
  ordered Morning, Afternoon and Night keys.
- `cadre_phase` exposes current mission and Off-Duty phase labels from the
  existing authorities. An empty list means there is no active phase record.
- `scenes` includes authorized scene IDs, chapter, span, planned participants,
  the viewer's separately tracked `joined` flag and a status of `scheduled`,
  `open`, `late` or `closed`. Discord snowflakes are decimal strings. The
  Handler can find new bindings in `unscheduled_scenes` and receives scene
  revisions for scheduling. Use `late_cut` for late writes. `entries` contains
  only records this viewer authored or received.
- `followups` contains authorized exact IDs and revisions. Resolve `play_choice`
  through the existing choice service, `medical` through the existing
  `MedicalService` recovery and `required_work` through the matching Requests
  workflow. The typed services check current ownership and applicability again.
- The Handler's separate `preview_cut` supplies the blockers. A player client
  can render its own follow-ups without receiving any blocker payload. A
  Director integration can observe the committed anchor through an authorized
  projection. Commands stay with the Handler.

The slice covers the offline service and synthetic workflow. Discord and
Activity routing, duration and deadline mechanics, and any out-of-character
reply-window controls are follow-on integrations. A proposed late mechanical
effect is adjudicated with existing rules commands or retained for review. The
late ledger has no generic resolution action that can change protected facts.

### Printed rules anchors

GIRL FRAME printed pages 120–121 (PDF pages 122–123) describe mission leadership,
the recovery transition and Gorgon movement when Off-Duty ends. Printed page
140 (PDF page 142) establishes Strain checks at the start of Off-Duty. In the
engine `OffDutyService.begin` opens preparation. Existing Strain services
record the three owned track outcomes before `CycleService.activate`.
`CycleService.finish` applies applicable world movement under the durable
period identity, with outstanding work still enforced. The calendar cut
records fictional time through its own receipt and does not call these
transition services.
