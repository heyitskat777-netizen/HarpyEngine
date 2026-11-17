# P2 assisted player testing

The engine-side candidate supports an **assisted offline player trial** with
invented scenes. A facilitator operates the local console, players supply their
own dialogue/choices, and the facilitator or an assistant supplies explicit typed
GM judgments. No paid model, live campaign capture or Discord Activity connection
is installed. This is the next human evaluation step, not autonomous-AI acceptance.

## Start here

From the repository with its pinned development dependencies:

```bash
.venv/bin/python tools/playtest_director_session.py --new var/my-p2-trial --demo
.venv/bin/python tools/playtest_director_session.py --resume var/my-p2-trial
```

Choose an unused directory for `--new`. The demo explicitly scripts the fixture
owners' choices and facilitator interpretation, completes one real native Keep,
confirms an outcome readback, assigns that approved information to the selected
roles and saves the campaign. It rolls once. It is a demonstration of the engine
contract; it does not emulate general model intelligence.

The second command reopens the same synthetic campaign for interaction. `/help`
lists controls. `--new var/another-trial` starts directly without the demo.
The current checkout also retains the demonstrated trial in
`var/p2-player-test-ready`; saved state is local and ignored by Git.

This is a **private facilitator console**. `/as lark`, `/as kite`, `/as handler`
and `/as gm` select synthetic test personas, not authenticated multiplayer users.
The facilitator relays only participant-permitted replies/readbacks to players;
GM packets, proposal files and private work lists stay private. Later Activity
authentication must replace this local fixture mechanism.

## What players test

1. Converse in an invented barracks, hallway or training scene. Ordinary text is
   IC input from the selected Pilot/Handler persona. A GM persona uses review
   commands; choose `/as handler` for fictional Handler speech. Engine-generated
   Handler replies appear only after a saved RESPOND decision. WAIT generates no
   Handler reply. Routine private GM WAIT reviews are diagnostics, not dialogue.
2. Request a Play explicitly, for example
   `GM, I choose Keep Your Head to hold the calibration needle steady.` Chat alone
   applies no outcome. With the same Pilot selected, run
   `/play {"play":"keep_your_head","heat":0,"trigger_confirmed":true}`.
   If omitted, the console takes context from that persona's last submitted text.
   The native service enforces the actual Play requirements and holds scene chat.
3. Each original owner uses `/choices`, `/decision ID` and `/choice ID JSON` or
   `/answer KIND JSON`. The shorthand requires exactly one matching own choice.
   For example `/answer tag_window {"options":["pass"]}` records that persona's
   explicit pass. It never answers for the other personas. Native result forms
   provide the legal choices; `/play` does not select Heat or options on its own.
4. The GM uses `/work` to find actual semantic sources and declaration reviews.
   `/bind $review $action` links the exact declaration to its native Pilot action.
   The engine proves scene, Play, author, incarnation and exact narration. A
   binding changes no mechanics; status follows the real action through completion.
   Other-role bindings remain manual where that specific proof is unsupported.
5. For Keep, `/frame JSON` supplies actual stakes, demands and source prerequisites.
   `/propose-next keep` exports a private request, proposal template and JSON Schema.
   Supply the judgment in `proposal.json`, then `/load REQUEST FILE`.
   `/review PROPOSAL` shows intended consumer fields, excluding private assessment
   notes. The actual original owner uses `/confirm PROPOSAL`; another owner rejects.
   A proposal alone does not commit an outcome, roll dice or bypass follow-ups.
6. After real completion, `/propose-next narration` supports an explicit approved
   readback referencing actual native result fields. `/narrations` returns each
   caller's native projection and intended approved text in saved order.
   Narration adds no canon effect. The GM can `/remember NARRATION_ID
   lark,kite,handler status` to retain that approved account for those actual roles.
   References are not inferred knowledge, automatic world changes or consent.

Use `/work` throughout. It separates native choices/required work, typed outcome
sources, proposal status and declaration status. An optional-Play question can
remain `needs_clarification` without any native Play being started. Use
`/triage REVIEW PLAY needs_clarification note` for explicit GM routing. Stale
proposals need a fresh request; unimplemented rules remain blocked/manual.

## Retry, memory and safety

- `/retry` repeats the original saved operation with its original key and resolved
  revisions under the original persona. It can resume after a provider failure
  or a clean console reopen. Native retries do not repeat rolls/effects.
- `/reopen` reconstructs session services. Exit and `--resume` reconstruct the local
  store and fake delivery state. This exercises engine recovery, not real Discord
  delivery or authenticated multi-client reconnect.
- `/pause` and `/resume` use native safety controls. Consent withdrawal or loss of
  authorization blocks optional session output; the console does not bypass it.
- `/memory` shows the GM's active references. `/remember SOURCE lark,handler topic`
  explicitly assigns a real source to those roles. `-` means GM-only reference.
  Supported topics: `general`, `objective`, `scope`, `status`, `briefing`,
  `tactical`, `debrief`. The last three explicitly enable queued Handler updates
  from that role's actual knowledge; reported claims remain claims.
- Active context is bounded to 100 references. `/archive ID,ID reason` explicitly
  retires selected references from prompts while preserving immutable history.
  Dependent references must be retained together or explicitly retired together.
  This does not erase fictional memories or simulate cross-scene time.
- Repeated unsolicited warnings about the same scope/roles stay silent after an
  actual saved Handler reply. A changed source briefing can rearm the warning;
  direct questions remain eligible. This is a bounded synthetic pacing policy.

## First human trial and feedback

Try one short scene with two players and a facilitator: ordinary conversation,
one actual Keep or Sensors workflow, explicit GM review, a safety pause and a
reopen. Check each player's own pending choices before ending. Shared table
outcomes use the GM-discretion policy; personal choices and private answers retain
original ownership. Do not enable unsupported rules to keep the scene moving.

Record the scene/action/proposal ID and concrete example for:

- A wanted GM/Handler intervention that was absent, or an interruption that felt unnecessary.
- A ruling that did not fit the actual goal, chosen traits or established fiction.
- Information a role should not have known, or player choice that appeared preselected.
- Unclear pending work, lost state, duplicate effects or inability to resume.
- Whether the session was understandable and worth continuing.

Save feedback locally beside the synthetic trial. No feedback is sent anywhere
automatically. Real-model quality, retention/redaction for real conversation,
connected Activity auth/delivery and live installation remain separate gates.

Verification and findings: [candidate report](../reports/P2_PLAYER_TEST_CANDIDATE.md).

## Campaign continuation

`/campaign-work` shows native mission controls, current Off-Duty progress and
campaign work owned by or concerning the current persona. `/campaign-work PERIOD`
reopens a particular native period. This read-only OOC view does not teach the
fictional Handler any information and does not enable another owner's controls.
The console still uses the trial's existing native release policy.

The automated connected mission rehearsal can be reproduced with:

```bash
.venv/bin/pytest -q tests/rules/test_p2_mission_cycle.py
```

It runs actual mission acceptance, contextual GM/owner-confirmed Plays, reward and
discipline work, all three selected Strain effects, both Pilot Off-Duty rolls,
individual scene acknowledgements, recovery, Status review and world advancement,
then dispatches the next mission in the same store. Its initial non-Void fixture
and specific low-severity Strain branches are declared test setup, not universal
rules coverage. This does not add mission/period write commands to the console;
use the native services/forms described in the
[consolidated Activity handoff](../integrations/activity/P2_SESSION_UI_HANDOFF.md).
