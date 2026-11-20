# Offline precise mission timing

This follow-on adds one opt-in timed sequence at a time to the offline
campaign-time package at `2228ce7`. A sequence belongs to an active mission,
an exact playable scene and the current fictional day. The Handler defines the
start minute, deadline convention, consequence when known, and options for
original mission participants. Players choose their own published options.

The first workflow covers direct actions, one native root Keep Your Head Play
and direct actions in an explicitly adjudicated parallel exchange. The existing
Play transaction saves a linked time receipt with the first roll. Existing
required responses and deliveries use the original action and roll. The
parallel workflow records each player's choice at the same anchor and leaves
the shared ending minute to the Handler. Unknown costs or consequences create
a durable ruling request. An action needing revised costs requires fresh player
confirmation.

Reuse the mission and native Play gates, campaign timeline, existing command
inbox, audit events and SQLite writer. Focused acceptance covers tunnel and
escort, both exact-deadline conventions, a saved Play with a required response,
retries after reopen, unknown costs and consequences, parallel adjudication,
safety and audience boundaries, and unchanged coarse time.

## Integration contract

The clock uses the existing HarpyEngine SQLite schema, campaign store, active
mission history and scene binding. Install the original campaign-time patch
first when applying the incremental patch. The combined integration bundle
contains both patches in order.

Construct `MissionTimingService` from `girlframe.services.mission_timing` with
the campaign's existing `OnboardingStore`. Resolve an authenticated
`GuildViewer` for each request. Keep the exact original request and the stable
command delivery key for retry. Both clients can consume
`CampaignTimeService.projection(viewer)` from the prior package.

| Command | Caller and contract |
|---|---|
| `open(viewer, key, mission_id, mission_revision, channel, scene_id, expected_anchor, start)` | Handler. Pass the active dispatch, scheduled scene and current campaign anchor receipt. `SequenceStart` contains an exact fictional minute and a `Deadline`. |
| `publish_options(viewer, key, id, expected, options)` | Handler. Pass the current clock revision. Publish a single Pilot's alternatives or direct options for distinct Pilots sharing a start. |
| `choose(viewer, key, id, menu_receipt, option_id)` | The original joined Pilot. The command either advances a direct action, saves a parallel or Play selection, or records a needed ruling. |
| `GameService.begin(..., timing_selection=receipt)` | The original Pilot. Pass a saved Play selection from `choose` to ordinary root Keep Your Head. The existing roll command charges the duration in the same transaction as the first dice receipt. Native follow-ups retain that receipt. |
| `withdraw_play(viewer, key, id, selection)` | The original Pilot. Withdraw an unrolled selection before a Play is attached or after its native cancellation. Save or cancel a recoverable Play through its existing controls first. |
| `declare_consequence(viewer, key, id, expected, consequence)` | Handler. Establish the missing fictional consequence and issue a fresh menu receipt. An affected single choice requires fresh player confirmation. For an unresolved duration, publish corrected options and request a fresh choice. |
| `resolve_parallel(viewer, key, id, expected, rejoin)` | Handler. Pass the latest revision and explicitly choose the common ending minute and account. Apply only the receipts already selected by human players. |
| `close(viewer, key, id, expected)` | Handler. Close after outstanding selections, rulings and native Plays resolve. The campaign calendar remains at its existing anchor until the Handler commits a separate cut. |

### Projection and boundaries

- `mission_timing` appears for the current Handler and original dispatched
  Pilots actually joined to the scene. The projection exposes `day`, `minute`,
  `deadline`, `deadline_status`, sequence `revision`, and an optional committed
  `consequence_receipt`. All clock values are integer minutes of that fictional
  day. For example, 18:20 is minute 1100. Discord snowflakes are decimal strings.
- A Pilot sees their options, duration and estimate flags, projected arrival and
  projected deadline status. Unknown costs have empty projections. Under
  `before`, equality misses. Under `by`, equality reads `at_deadline` and is
  on time. The declared consequence is recorded on the first miss.
- A parallel selection leaves the shared clock at its quoted starting minute.
  The Handler confirms the common ending manually. Exact durations must fit in
  the chosen interval. Estimates can be adjudicated with the Handler's account.
  The service neither sums parallel work nor automatically chooses the longest
  duration. Absent participants receive no implied selection.
- The Handler and affected Pilot can see their pending ruling where applicable.
  A resolved ruling refreshes the menu. Current clock revisions fence Handler
  commits, and menu receipts fence player choices.
- Time effects are limited to the clock ledger and the already declared
  fictional consequence. Use the existing rules services for any injury,
  resource spend, mission result or rules transition. Waiting for Discord,
  reading the projection, and delivery retries consume zero fictional minutes.
- This release covers same-day sequences, direct parallel actions and one native
  timed root Play. Cross-midnight clocks, additional timed Play adapters and
  Discord/Activity command routing are follow-ons.
