# Connected mission lifecycle results

Implemented source/tests: `bd2deb3`, continuing the connected-scene candidate
`d42dbc4`. The native mission → rewards → complete Off-Duty → next mission
rehearsal now passes in one persisted synthetic campaign. The engine-first Activity
requirements are consolidated in
[the session UI handoff](../integrations/activity/P2_SESSION_UI_HANDOFF.md).

## Delivered behavior

`DirectorSessionService.campaign_work(viewer, scene, period_id=None)` joins native
mission controls, current/selected period review and unresolved work owned by or
concerning the viewer. It uses the original native recipient projections: private
Pilot/Handler scenes remain private and decision subjects do not gain their
inflictor's authority. It is a read-only OOC dashboard, not fictional Handler
knowledge or a generic execution endpoint. The local console exposes it through
`/campaign-work [PERIOD]`; native campaign write forms/services remain separate.

The new end-to-end scenario performs:

1. An actual offer, separate acceptance by both Pilots and Handler dispatch.
2. A source-bound Keep declaration, actual roll/traits, private contextual GM
   proposal, original Handler-owner confirmation and approved outcome readback.
3. Native success/debrief and Permissions rewards: the current Ace receives two,
   the other participating Pilot one. Exact mission-end retry after database
   reopen preserves those rewards without duplication.
4. The real Dog discipline task. Mission completion remains blocked until its
   actual Handler decision owner applies the native effect. The subject cannot
   supply that owner's answer.
5. A real preparing Off-Duty period, factual Strain review, three saved dice,
   selected columns and all three typed effects: a Directed Gorgon, a rebel cell
   and room reassignment. A new mission remains blocked during the period.
6. Both Pilots' real Go Off-Duty rolls and Frame-reward reviews; a barracks scene
   with individual acknowledgements; each owner's recovery; a separate Handler
   scene and its participants' acknowledgements; Status review and actual world
   advancement. A database reopen retains pending progress. No required period
   work remains when the period completes.
7. A new native scene with explicit scoped memory handoff, a second mission's
   individual acceptance/dispatch and another contextual owner-confirmed Play.
   Status order changes from `(2, 3)` to `(3, 2)`. There are four native Play
   receipts: two Keep and two Go Off-Duty. The second mission remains active as
   the next playable starting point, rather than claiming another full cycle.

The scenario starts from the same explicitly authored non-Void baseline used by
the existing low-Strain Off-Duty fixture. Initial Void flags are set before the
rehearsal; this is not a demonstration of surgery/removal mechanics. The three
specific effects are `strain.void.low.1.1`, `strain.rebellion.low.1.1` and
`strain.budget.low.5.2`. This proves their connected normal flow, not all severity
branches, recursive events, specialist rules or all-type coverage.

## Findings and changes

The missing integration was campaign work visibility in the Director session.
The native reducers already supported the lifecycle; no replacement state machine
or mechanical approval shortcut was necessary.

The rehearsal initially stopped at genuine source requirements: success still
left Dog discipline work, and a routine Off-Duty result could not select the city
scene offered by a high result. The final test uses actual discipline and a legal
barracks choice. These are explicit requirements in the UI handoff. Handler scene
Status review likewise remains blocked until each real participant acknowledges.

Read-only projection checks leave canonical state and event count unchanged.
Privacy checks exclude a Pilot-only scene from the Handler view, exclude a
Handler/Pilot scene from the other Pilot view, keep private reasoning out of
approved readback, and keep private scene prose out of event/command metadata.
Carried Pilot notes remain absent from fictional Handler context.

## Verification

- Final focused run: **53 passed in 44.90s**, zero failures/errors/skips.
  JUnit: `var/p2-mission-cycle-final.xml`; log: `var/p2-mission-cycle-final.log`.
  It includes the connected cycle, console, Director session/continuity, native
  missions, Off-Duty, Strain effects, discipline and Activity integration controls.
- Global Ruff lint and formatting pass (2,054 Python files formatted); global
  mypy passes for 956 source files. Runtime registry, original planning contracts,
  offline CLI health and repository checks pass with zero repository findings.
- Reproduce the connected scenario with
  `.venv/bin/pytest -q tests/rules/test_p2_mission_cycle.py`.
  Its synthetic result is saved as `var/p2-mission-cycle.json`.

No new full regression, supplied Activity-bundle test run, browser acceptance or
human playtest was performed. Earlier evidence and integration ZIPs remain tied
to their earlier source; this increment does not relabel them as current results.
GM assessments are fixture-authored typed proposals, not a real-model evaluation.
No spending, model calls, real capture, live campaign writes, deployment, restart,
release-policy change or Discord publication occurred.

## Review and next priorities

The named connected engine rehearsal is complete. The next useful work is to
implement the consolidated Activity session surfaces against a pinned engine
candidate, then verify actual authentication, recipient state, reconnect/retry,
source-owner confirmation and private/public rendering in the browser. This task
supplies the contracts and acceptance sequence; it deliberately leaves frontend
installation deferred under the owner's engine-first instruction.

After that, run a short facilitated human trial for readability, desired GM and
Handler interventions, contextual rulings and pacing. That feedback is more useful
now than adding another broad synthetic scene generator. Broader branch review,
conditional GM fact bridges and real-provider quality remain separate work;
unimplemented or unapproved sources must retain their native blockers. Run a fresh
full regression when freezing the next integrated player-test release candidate.
