# P2 engine-side assisted player-test candidate

Base: `fccde43` (typed native GM consumers at `e3a11f7`, 195 focused CI passes).
Owner directed sustained synthetic sessions and continuation until P2 is ready
for player testing. Activity UI work, spending and live installation remain
separate. This deliverable prepares **assisted offline player testing**; it does
not claim connected multiplayer availability or autonomous AI-GM acceptance.

## Delivered session flow

`DirectorSessionService` coordinates saved input → discrete GM review → engine
Handler RESPOND/WAIT → actual native work → typed GM proposal → original-owner
confirmation → permitted completed-outcome readback. Work lists expose actual
pending sources, proposal freshness/confirmation and declaration status. Native
choices, dice, costs, original owners, safety, release gates and follow-ups remain
in the original services. There is no general effect-execution endpoint.

The private local console persists a synthetic campaign, personas, resolved retry
arguments and fake delivery state. A clean process reopen can finish a held Play
without another roll. GM packet/proposal files and directories are private. Its
fixture personas are a development harness, not a substitute for future Activity
authentication. An explicit demo and a short player-test guide make the candidate
usable before Activity UI work.

Explicit reference retirement preserves append-only source history and dependencies
while keeping at most 100 active references. The focused memory case retains 125
historical references with 75 active after retirement. Approved native-outcome
readbacks can become `approved_outcome` references only through explicit GM role
assignment, after checking their real native completion, confirmed proposal,
original audience and exact approved text. Narration is an approved account;
it is not another mechanical/canonical effect. No fictional forgetting, general
cross-scene causal clock or automatic prose summarizer is claimed.

## Sustained scenes and review

Four independent scenes each supplied **100 scripted Pilot inputs**. There were
**seven native Plays/seven rolls**, 35 engine Handler responses and 365 WAITs.
Handler count was observed, not prescribed. GM conversation, fixture-authored GM
proposals, native owner confirmations and approved readbacks have distinct labels.
No hidden expected success label is passed into a general-language evaluator:
Keep uses explicitly annotated facilitator trait relevance and actual committed
traits. This exercises the proposal contract, not autonomous language understanding.

| Scene | Handler responses / WAIT | Native Plays | Contextual outcome |
|---|---:|---:|---|
| Barracks readiness | 9 / 91 | Keep, Sensors | Mid control supports the stated precision goal |
| Hallway meeting | 8 / 92 | Keep, Sensors | Low toughness supports the endurance goal |
| Simulated relay mission | 10 / 90 | Keep, Engage | High Keep lacks control and fails precision; Engage retains actual maneuvers |
| Relay tactical exercise | 8 / 92 | Assault | GM determines shared advantage; native target Asset changes; real Handler grant supplies escalation |

All scenes finish with **zero pending native choices/required work**, no unnarrated
completed native actions and matching roll counts. Questions about possible Plays
can remain explicitly marked for clarification; they are not silently converted
into actions. All scenes exercise source history beyond the latest-100 raw-input
window, retained explicit references, service reopen, exact replay, a safety pause
and private-canary exclusion. Scene labels frame independent synthetic fixtures;
they do not prove travel, actual mission acceptance or a campaign-wide clock.

Reproduce with:

```bash
.venv/bin/python tools/run_p2_session_trials.py
```

Readable local output: `var/p2-session-trials/index.html`, per-scene JSON/HTML,
`transcripts.txt` and `summary.json`. GM private reasoning is excluded from these
transcripts. Source files and evidence commands are retained in the repository;
generated synthetic databases and transcripts remain ignored local artifacts.

Material findings fixed during review:

1. Repeated scope plans could repeatedly summon the Handler. A successful saved
   reply now suppresses the same unsolicited warning for the same actual roles and
   scope sources. A failed reply does not suppress retries; direct questions and
   changed briefing sources remain eligible.
2. A confirmed battle context could reappear from its older proposed history.
   Adapters and work lists now select the latest context per ID. A closed source
   cannot reopen as a pending judgment. The affected relay case was rerun.
3. Keep owner review exposed nested assessment notes. Only intended verdict and
   narration now enter that review; top-level and nested private-reason canaries
   are checked. Full reasoning stays in the GM-private proposal.
4. Natural `I call`/`I choose` declarations were not recognized. Explicit forms now
   route to the Play review; conditional discussion remains uncommitted. Exact
   declaration/action binding prevents a completed Play leaving a misleading
   pending referral, without granting source metadata authority over mechanics.
5. Long sessions needed an explicit retained-knowledge/archival path. Approved
   outcome references and retirement now support that path without broadening
   the Handler's knowledge or deleting original evidence.

An initial four-scene run failed on the stale battle-source listing. An earlier
harness run used the wrong final source owner and rejected correctly. These were
corrected, then affected/final runs repeated. No failing test is hidden or removed.

## Readiness and boundaries

[Player-test guide](../docs/P2_PLAYER_TEST_GUIDE.md) supplies the actual commands,
roles, private review flow and feedback checklist. First human pacing/fairness
acceptance remains pending. Broad real-model narration, provider transport/usage
limits, real conversation retention/redaction, Activity auth/publication and live
rollout remain unfinished and disabled. Conditional/unimplemented source mechanics
retain their existing manual/native workflow or blocker. `RULES_SUBSET` remains;
review coverage across 63 entry points is not full published-rule certification.

No paid call, real campaign capture, live migration, bot restart, deployment,
production version change, external message or private-runtime edit occurred.
Final exact-source verification is recorded below after checks complete.

## Recorded local verification

- Final focused selection: **201 passed in 216.19s**, zero failures/errors/skips;
  JUnit at `var/p2-player-candidate.xml`. Includes sustained-session, persistent
  console/native retry, memory/knowledge, nested privacy and latest-source checks.
- Four-scene final runner: **400 Pilot inputs, seven actual native Plays/rolls,
  seven completed action bindings**, 35 Handler RESPOND / 365 WAIT. Two incidental
  questions remain explicitly marked `needs_clarification`, with no native action
  manufactured to answer them. No native required work remains pending.
- Standalone `--new var/p2-player-test-ready --demo` and a separate-process
  `--resume ... --commands ...` both passed with saved state and no rejected command.
  Their demonstration choices/judgment are fixture-authored, not human acceptance.
- Changed Python lint/format: **17 files** passed. Applicable typing: **seven
  source files** passed. Runtime registry, planning-package contract, offline health
  and publishable-file/manifest checks passed (zero repository findings).
- The original planning package and frozen live runtime were not changed. This is
  focused candidate evidence; the full project regression and human/real-model
  acceptance were not run or claimed.
