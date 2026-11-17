# Reviewed worldbuilding into connected testing

Core and connected-trial source: `525172e`, based on `f4a40ec`.
Final API recovery/access hardening: `92c3a90`.
The owner requested the worldbuilding proposal workflow through incorporation
into testing. The first bounded workflow is implemented, including native world
commitment, deliberate knowledge disclosure and a world-driven native Play.

## Implemented behavior

`DirectorSessionService.worldbuilding` opens a private source-bound packet,
accepts a typed manual/provider proposal, records explicit GM review and routes
confirmation to the actual native world owner. GM and native owner can be
different people; GM visibility does not confer another person's world authority.
The native world subsystem retains its existing release approval and pending-Play
locks. No model/provider is installed or scheduled by default.

Supported actions:

| Action | Actual consumer and limit |
|---|---|
| Setting detail | New append-only canonical narrative record attached to a real existing location, NPC or faction |
| NPC/faction goal | An intention under native world authority; goals for another controller's NPC reject |
| Complication | An unresolved situation or question; no automatic resolution, harm or clock tick |
| Ordinary NPC introduction | Existing WorldService NPC consumer; pristine owned NPC only, preserving native role/source restrictions |
| Ordinary faction introduction | Existing WorldService faction consumer; actual entities/board references and no imported consequence state |

Each narrative key has one active version. Revising it requires the exact current
predecessor and unchanged kind/subject. Previous text, version, author, native
event and proposal provenance remain in canonical history. These records do not
mutate damage, resources, conditions, custody, movement or player responses.
Mechanical consequences still require the original native source-specific paths.

Packets bind current canon, actual source, source revisions, references, scene
frontier, consent/safety and authority. Input/canon changes invalidate unconfirmed
work. Unsupported effect fields reject. A GM must still review free prose for
continuity, causal relevance and improperly claimed effects; structural validation
does not establish those semantic judgments. A test deliberately accepts such
prose structurally, rejects it at GM review and proves no native mutation.

Native confirmation is idempotent independently of the caller's retry key.
If the native write succeeds before a private receipt failure, retrying recovers
that same result. Private/pending status explicitly reports
`native_committed_recover_receipt` for that case. Fault injection verifies the
recovery without a second world record. Metadata-only work remains readable
without optional world capability, with guild/member and role authorization intact.

## Knowledge and disclosure

World commitments stay outside fictional Handler/Pilot/NPC knowledge until an
explicit disclosure selects a unique exact quote and actual current recipients.
Disclosure and its knowledge reference commit in one transaction. Neither private
reasoning nor an undisclosed agenda/body enters the reference.

Only native-proved `world-disclosure:` sources qualify as `approved_world`;
raw `world-commit:` IDs and player prose cannot teach authoritative world facts.
References use `established_world`. A later character relay remains an attributed
`reported_claim`, preserving the difference between world authority and testimony.
The knowledge acquisition path cannot widen recipients or replace the selected
quote with different text.

Historical disclosure is validated against its original reviewed native event,
not whichever development version is currently active. Same-controller NPC
knowledge survives native scene closure, explicit next-scene casting and scene
continuity. An NPC's human controller does not thereby teach their own Pilot.
Consent withdrawal blocks carried prompt use. Original recipient/controller changes
require explicit reconciliation or a fresh disclosure; historical records remain.
Read-only integration review caught and fixed inconsistent open/closed controller
checks before the final affected selection.

## Connected rehearsal

```text
.venv/bin/python tools/playtest_worldbuilding.py --directory var/p2-worldbuilding-final-20261117
```

The rehearsal extends the retained 112-input session with explicit fixture GM
interpretations. Barracks, hallway, simulation and debrief are fiction labels in
one engine scene; they do not assert native travel.

| Result | Observed evidence |
|---|---|
| Player inputs | **112** |
| Native world commitments | **7**: one NPC, one faction, five narrative history entries |
| Active narrative entries | **4**, retaining both original and revised private NPC goals |
| Scoped world disclosures | **3**: archive detail to Handler, then Lark; scheduling complication to Lark |
| Role privacy | **112** Handler projections and **13** actual generation requests exclude both private agendas and their record IDs |
| Handler guidance | The archive answer cites the actual disclosed world reference and grants no new access permission |
| Native Plays | **3** completed, using **3** actual rolls; no pending native choices |
| Player response | The existing actual controller handoff preserves voluntary listening without forgiveness |
| Persistence | Service reconstruction and actual database reopen add **0** world writes and **0** rerolls on replay |

The new scheduling complication directly motivates the first native Keep. Its
actual source declaration and native action context match. The GM proposal and
trait assessment cite the exact disclosed world reference. The approved readback
states:

> The pilot compares the conflicting maintenance schedules methodically without rushing. Which schedule applies remains unresolved.

Success establishes the narrowly declared methodical comparison; it does not
invent which schedule is authoritative. Sensors and the later social Keep retain
their native consumers/owners. The complication's canonical record remains current
and unresolved after the Play. The goal revision preserves its earlier version.

All long-scene dialogue, GM interpretations and confirmations are explicit local
fixtures. This is a connected engine rehearsal, not an autonomous model campaign.
The initial trial is preserved separately; the final trial adds the direct
complication-to-Play path and third disclosure.

## Independent proposal audit

One fresh internal agent was explicitly configured as `gpt-6.1-terra` and received
three actual pre-proposal packets plus the exported schema. It did not receive
source code, fixture proposals, expected actions or trial results. It proposed a
modest barracks detail and two owned mechanic intentions, preserving player choices
and the difference between a reported objective and established mission facts.

**3/3 proposals passed first-pass schema and frozen native-domain validation**
without repair. These were archived packet validations, not new native writes or
fresh confirmations. All three sampled outputs were narrative developments;
independent model output for NPC/faction introductions was not sampled. The audit
is separate from the fixture-driven 112-input rehearsal and is not a production
API, cost, latency or general model-quality benchmark.

## Verification and handoff

- Integrated affected selection: **55 passed in 53.04s**,
  `var/p2-worldbuilding-integrated.xml`.
- Final affected selection on the hardened API: **14 passed in 18.07s**,
  `var/p2-worldbuilding-final.xml`. Includes actual NPC closed-origin continuity,
  world knowledge/workflow, session and cross-process restart checks.
- A final narrow recovery/access selection passed **2 tests in 2.41s**. These
  selections overlap and are not additive. No full regression or remote CI run.
- Initial development smoke had three fixture failures: the bare M2 fixture had
  no synthetic world approval, and fault injection patched the wrong GameService
  instance. Corrected setup then passed all seven native/knowledge checks; native
  gates were preserved. Existing tests were not weakened.
- Global Ruff lint/format pass (**2,087 Python files**) and mypy passes
  **962 source files**. Runtime registry, retained planning contracts, offline
  CLI health and repository checks pass. Four new test files are in focused CI.
  Rules and release approval records remain unchanged.

The [consolidated Activity handoff](../integrations/activity/P2_SESSION_UI_HANDOFF.md)
documents proposal/review/confirmation/disclosure controls and receipt recovery.
These are Python service contracts; no authenticated HTTP routes or frontend
installation are implied.

Final artifacts are under `var/p2-worldbuilding-final-20261117/`, including a
readable worldbuilding transcript, event/results, prompt projections, replay
records and compact evidence ZIP. Initial packets and independent outputs remain
under `var/p2-worldbuilding-connected-20261117/`. Synthetic databases and saved
runtime configuration are excluded from the evidence bundle.

The workflow is ready for facilitated synthetic testing. Rich autonomous NPC
dialogue/strategy, map expansion, automatic faction actions, timed world simulation
and source-specific mechanical event bridges remain separate work. The first
version records goals and hooks rather than automatically executing them. Human
story quality and pacing acceptance remain pending. No external API spending,
real campaign capture/write, live rollout, bot restart or Discord publication occurred.
