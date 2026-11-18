# P2 reviewed Handler and Director model adapters

HarpyEngine now has a bounded server-side Responses adapter and a local Activity
desk for the reviewed Handler workflow. The supplied Activity archive is verified
and overlaid in a disposable checkout. The lab uses an in-process fixture
transport. No paid calls, real campaign transcripts, or Discord sessions were used.

## Handler sheets and NPC authority

The appointed Handler already has a native, privately saved character sheet.
Activation selects one of the seven playbooks. Its derived profile supplies voice
and eligible optional cues, alongside the individual dossier and role-filtered
knowledge. The Activity adapter exposes the sheet to the authorized Handler.
Only an engine-approved `RESPOND` reaches the speech adapter. The facilitator
reviews the draft, then the actual Handler previews and delivers it to the
approved audience. The local review control selects the originating Pilot.

The facilitator's private roster displays living canonical NPCs, including ones
outside the current scene. The actor must be valid in the native scene cast to
receive a reaction request. A new NPC introduced by the native Support Play is
also canonical, with the actual Handler as controller. The Play does not cast
that NPC in a scene or expand the Handler's knowledge. NPC reaction requests
receive that actor's own context. The controller's approved response remains a
private candidate. Publication to the timeline and subsequent listener knowledge
are pending a dedicated NPC delivery workflow.

## Director and engine authority

The model can propose a typed ruling from a native Play, a grounded worldbuilding
addition, an actor reaction, or a Handler cue for review. Play input uses the
actual action and its recorded evidence, and excludes the full campaign snapshot.
Worldbuilding receives relevant current Fronts as pressures. The engine still
checks scope and freshness, and only native workflows can commit effects. A due
Front remains ready for attention. Table outcomes stay with the human GM.

## Local verification

- 59 focused engine tests passed. They exercise all seven Handler sheets and
  voices, all ten Handler Plays, quiet turns, knowledge isolation, native Support
  ownership, typed Keep Your Head, private worldbuilding and NPC reactions,
  scoped Front context, wrong-owner rejection, and retry/replay.
- Eight supplied Activity tests cover the patched source. Chromium separately
  exercises local account sign-in, the scene composer, facilitator review,
  Handler preview and delivery, wrong-owner denial, reconnect, manual closure,
  and consent withdrawal. The typed Keep ruling is verified through the engine
  and Activity adapter. The default browser fixture configures the Handler client.
- The transport caps attempts, input size, output tokens, and request timeout.
  The attempt budget is process-local. A later supervised provider trial still
  needs an approved model and provider-side budget. Provider compatibility,
  live Discord authentication, and play quality with generated responses remain
  to be evaluated.

- [Activity UI handoff](../integrations/activity/P2_SESSION_UI_HANDOFF.md)
- [Adapter tests](../tests/test_director_model_adapters.py)
- [Local test results](../var/p2-model-adapters-final.xml)
- [Chromium smoke output](../var/p2-model-activity-browser.json)
