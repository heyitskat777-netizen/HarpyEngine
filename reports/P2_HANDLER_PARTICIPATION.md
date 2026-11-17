# Handler participation in the sustained campaign

The previous 601-input run had 49 Handler replies, all prompted by direct
questions. It exercised call-and-response well and left proactive participation
largely untested. This change connects the existing intervention gate to reviewed
Handler speech, the Handler’s own fictional actions, and a native briefing Play.
Implementation is on `610092a`.

The reviewed provider receives the persisted response reason and the actual
Handler’s current dossier. Its profile and remembered experiences come from the
Handler’s own projection. A separate GM dossier note, another pilot’s personality,
and undisclosed information stay outside the request. The game still decides
whether to open a reply. Briefing updates, tactical reports, scope warnings, and
reviewed response needs can qualify. Once an approved exchange addresses a known
update, the engine suppresses repeats, including after scene carry.

A response may describe something the Handler does, such as putting an updated
brief beside a route map or marking a pilot report separately from confirmed
contacts. This field is reviewed with the dialogue as a fictional contribution
within the private exchange. A formal briefing offer requires an eligible scoped
intervention and citations the original recipient already knows. The Handler’s
controller starts the native grant and confirms its exact reviewed wording
through the existing outcome service. The grant only permits the briefing Play.
Completion creates a native notice for the original recipient. Other native
Handler Plays keep their existing triggers and controls.

The convoy case also exercises a private question about a pilot’s intent while a
Keep Your Head is pending. The acting pilot supplies the answer, and the GM’s
resumed ruling cites that answer. The locked in-character channel, original roll
and traits, and separately owned target choices remain in force.

## Rehearsal evidence

Both the 73-input workflow check and the 601-input campaign completed all four
missions and both Off-Duty periods. The longer run produced **54 Handler replies**,
including **5 proactive interjections** with reviewed in-scene actions, and **547
WAIT decisions**. The previous run recorded 49 direct replies and zero proactive
interjections. Anchor used the briefing Play twice. The original pilot received
each notice after the Handler controller confirmed it. The four briefing updates
and the public reconnaissance report generated one proactive intervention each.

| Input | Situation | Handler contribution |
| --- | --- | --- |
| 3 | Spillway Relay. Latch starts work with a fresh briefing available. | Places the briefing beside the route map, speaks to the known access limits, and completes a native briefing Play. |
| 152 | Glass Orchard. A new limit applies to the reconnaissance mission. | Brings the current briefing into the scene before the pilots proceed. |
| 202 | Latch reports an amber silhouette, identity unconfirmed. | Marks the reported location separately from confirmed contacts and keeps its identity open. |
| 304 | Two Convoys. Two requests compete for one inspection window. | States the constraint and completes a native briefing Play without choosing anyone’s cooperation. |
| 455 | Last Cable. The team learns the override is protected. | Sets out the updated constraint before the extraction attempt. |

The convoy clarification resumed from Latch’s own private answer on the original
roll. The original target refusal and subsequent acceptance both remained in the
record. Comparison against the previous full run matched the pilot rulings, Heat
spends, mission outcomes, rewards, discipline and Status. All 17 pilot Play
receipts remained accounted for. The two Handler Plays were separate native
briefings. Database reopening and replay created no new events. There were no
pending native choices at the end.

The audit covered 601 scoped Handler projections, including a matching own
persona in each, plus all 54 persisted provider inputs and reviewed replies.
All reply citations were present in their corresponding role packets and the audit
detected none of the tested private facts or dossier material. The comparison and
role audit outputs are retained with the campaign.

```bash
.venv/bin/python tools/playtest_sustained_campaign.py --directory var/p2-handler-participation-20261117
```

See the [full transcript](../var/p2-handler-participation-20261117/campaign-transcript.md)
for the marked actions and Plays. The reduced run is in
`var/p2-handler-participation-smoke-20261117/`. Both runs
use the same Latch, Flint and Anchor fixture cast and the existing native mission,
Play and Off-Duty services. The fixture provides dialogue and proposed rulings.
The provider uses Anchor’s dossier voice and scripted response patterns, so the
output demonstrates the new routing and authority. A human pacing or real-model
evaluation would test different questions. Model calls and cost were zero.

## Verification

The affected suite passed 56 tests. The final source also passed 16 focused tests
covering Handler review, scoped initiatives and controller response handoffs.
The counts overlap. Ruff, mypy, the repository scan, the rules registry check and
the original planning verification passed. A pre-existing native counter test
was adjusted to mock a single callback. Its earlier module-wide stub prevented
an unrelated import during the combined selection.
