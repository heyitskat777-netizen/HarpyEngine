# P2 Activity scenes and closeout

The supplied Activity lab now has an optional offline overlay for Relay
operations. In an opted-in Director room, the existing composer posts to the
engine timeline. It distinguishes public speech from narration for review.
The transcript projects each viewer's latest visible inputs and delivered
Handler contributions on their recorded order. Rules and facilitator packets
remain on their own routes. The ordinary Activity path is still available
outside the opted-in room.

## Scenes and knowledge

Parallel native scenes keep their live observations and replies separate. A
scene without the Handler can still accept inputs and resolve native work.
The Handler route records WAIT for those turns. The continuity service also
rejects a carry request from an open source scene.

The documented manual close command uses the existing native closure checks
and atomically files a report for the actual Handler. It includes current
references she already knew in the scene and any selected public Pilot reports
that the engine can trace to an actual accepted source. The native close
rolls back if a selected reference is private or invalid. Source transcripts
stay with their original audience. Reports enter the Handler's private memory
in later scene requests, including an already-open parallel scene. They do
not trigger announcements by themselves. Use current-scene approval and
disclosure before sharing new facts with a different audience.

The report remembers its actual closed scene, original Handler, roster and
consent generation. Rebinding the old channel does not move the report to
the replacement scene. An original participant can still withdraw use of the
report after rebinding. The engine then drops it from Handler recall.

## GM work from a native Play

Native action and choice IDs make eligible typed GM work discoverable. An
actual Keep Your Head was started through the native Play service, rolled once, and
committed its original Pilot traits. Its pending choice appeared as GM work
under the same action without any chat declaration. The fixture proposed a
typed ruling, rejected a wrong-owner confirmation, and completed through the
original owner. The final read used the native result.

The offline transport patch mounts recipient and facilitator routes under
the existing lab session middleware. Browser-facing endpoints preserve
command keys and expected revisions. The integrated Relay composer and
transcript are present. Facilitator review, closeout, and typed ruling actions
are available through the adapter routes. Dedicated Activity controls for
those actions and a real Discord OAuth client pass remain open.

## Reproduction

From the engine checkout, prepare a disposable copy of the Nov 16 source bundle.

```sh
.venv/bin/python tools/verify_activity_bundle.py \
  --source /workspace/source-handoff-2026-11-16 \
  --output var/p2-activity-lab-demo --p2-routes --prepare-only
```

The verifier checks the original manifest before applying the overlay. The
browser smoke script opens the copied lab, creates a fresh synthetic campaign,
launches three separate browser sessions, and shuts down the local lab. Supply
the paths to the local Chromium and Playwright installation if needed.

```sh
node integrations/activity/verify_p2_lab.cjs \
  var/p2-activity-lab-demo/app/harpy-activity-lab .venv/bin/python \
  /usr/bin/chromium /opt/codex/cua_node/lib/node_modules/playwright
```

The fixture flag is limited to loopback lab mode. No real transcript capture,
external provider spending, Discord connection or deployment was used.

The affected engine selection passed 45 tests. The final closure guard passed
11 focused tests, with overlap. Eight supplied Activity tests passed against
the patched source. Chromium verified the local session, engine-backed composer,
scoped Handler delivery, wrong-owner denial, reconnect, closeout and consent
withdrawal. The typed Play ruling is covered by the engine/adapter test.

- [Activity session handoff](../integrations/activity/P2_SESSION_UI_HANDOFF.md)
- [Engine tests](../tests/test_director_activity_scene.py)
- [Browser smoke output](../var/p2-activity-browser.json)
