# Sustained synthetic pilot campaign

The final long run and separate artifact audit passed. Implementation is frozen at
`ef9d2ddd07197e037b30316ce1ca60d8487a23d4`, continuing the Living Campaign foundation.
No engine rules, release policy or live process was changed. Milestone labels
remain unchanged. All actors, inputs, dice and approvals are synthetic; external
model calls and cost are zero.

## Cast and method

| Character | Personality and tension |
|---|---|
| Mara Saye / Latch | Precise, dry and cautious. Values accuracy and consent; wants certainty but knows delay can also hurt people. |
| Iona Vale / Flint | Blunt, restless and protective; jokes when afraid. Wants speed to serve care, and gradually checks hardware before relying on confidence. |
| Corin Hale / Anchor | Brief, calm and evidence-focused. Provides structure without choosing pilots' cooperation or claiming unreported information. |

These are NPCs in the rehearsal's fiction, driven by simulated owners. The pilots
use real native Pilot identities and MOCKINGBIRD/JANUS sheets. Ordinary engine
Npc records cannot substitute for Girl/Frame Play actors. Callsigns are portrayal
labels, not authorization or storage keys. Each role has its own versioned dossier,
private fears and controller-authored goal; experiences accumulate after missions.
No original campaign cast was imported.

This is a reproducible fixture campaign, not an autonomous model trial. Dialogue
uses personality templates; a bounded synthetic GM proposes contextual judgments
from actual chosen traits and target responses. The engine validates proposals,
requires original owners, rolls real native consumers with injected test dice,
and applies accepted costs/consequences. Mission reviews remain explicit
facilitator decisions based on accepted task results. No external Terra API ran.

## Campaign sequence

1. Spillway Relay: restore a public relay in a flooded gallery, with no supplied
   access code for a sealed gate. A rushed precision attempt and a cold-endurance
   alternative test that different goals need different traits.
2. Glass Orchard: reconnaissance from a fogged gantry. A private pilot observation
   stays unreported, while public silhouettes remain attributed uncertain claims.
   An attempt to obtain private access through confidence tests a high Keep result.
3. Two Convoys: competing inspection windows. A pilot declines a proposed sequence,
   a vague task requires facilitator clarification, and a later voluntary
   alternative is answered through the actual controller handoff.
4. Last Cable: frozen cargo coupling with an inaccessible override. Failure to
   recover cargo does not become success merely because another task was attempted.

Four actual native scenes are connected by explicit scoped memory carry. The
locations above are fictional scene descriptions, not unperformed board travel.
Missions1–2 run consecutively, followed by a complete native Off-Duty cycle;
missions3–4 and a second full cycle follow. No active period is skipped. Each
cycle resolves three saved Strain dice and typed consequences, both pilot rolls
and recovery, actual Handler-scene acknowledgements, Status and world advancement.

The initial non-Void fixture is explicitly authored before testing. This does not
demonstrate surgery, Void removal or every Strain severity branch. Repeated low
Strain events can change later severity; a third recovery cycle is outside scope.

## Results

The full run accepted **601 rehearsal IC inputs**:597simulated pilot inputs and4Handler
briefings, across4native scenes. It produced9contextual Keep rulings,4Sensors
answer workflows and4Go Off-Duty rolls: **17native Play receipts**, plus6separate
saved Strain dice. Both Off-Duty periods completed and all native choices closed.
Each actor's dossier reached version5 without changing identity.

| Mission | Result and GM response | Cumulative Permissions, Latch / Flint |
|---|---|---|
| Spillway Relay | Success through a cold-endurance alternative. Flint's9-total precision attempt failed; Latch's5-total tough endurance attempt was enough. | 2 / 1 |
| Glass Orchard | Success for the located report. A12-total attempt did not supply a protected gate code or establish control. The unreported contact stayed outside Handler knowledge. | 4 / 2 |
| Two Convoys | Success after an initial declined proposal, explicit facilitator review of a vague task and a separately accepted alternative. A refusal was not overwritten by prose. | 5 / 4 |
| Last Cable | Failure: cargo unrecovered. Totals12and16 did not establish the required control/access; the mission was not relabelled successful. | 6 / 6 |

Native mission rewards still apply according to participation/Status on failure;
the test does not impose a new zero-reward-on-failure rule. Five actual discipline
applications resolved their original source obligations, including overlapping
failure/Dog work. Status changed through authorized review to(3,2), then(2,3).
Two native world advances applied the typed Strain outcomes; chat alone did not
advance the campaign.

Handler gates were **49RESPOND / 552WAIT**:49direct questions,535social turns
with no need,17GM-addressed turns. All49drafts received explicit synthetic GM
review. One eligible existing Director batch completed with WAIT and no speech.
That is a routing test; direct-question frequency is deliberately artificial.

The separate saved-artifact audit checked **601actual Handler request packets**,
49reviewed replies and609role-audit groups. It searched for GM and pilot-only
markers, the unreported contact's descriptive fragment, and other actors' private
fears. **0tested leaks were detected**, and every Handler citation remained in
its actual request's scope. Private own-role dossiers remained separate from
GM notes and other actors' views.

The reduced73-input rehearsal and full601-input run had identical contextual
rulings, native costs, mission outcomes, rewards and Status. Each used an independent
synthetic store. Extra chat caused no extra mechanical progression. After full
database reopen in the fourth scene, input retries and native confirmation retries
returned the same results with **no new canonical state or events**.


## Findings to retain

- Actual Heat persists between missions. A zero-spend declaration becomes illegal
  when the actor holds five or more Heat. The fixture now reads the current budget,
  spends the required amount and chooses according to the actual resulting tier.
  Higher totals do not guarantee the selected task is possible.
- A single applied consequence may satisfy overlapping obligations. Refresh each
  task after effects; do not apply a stale work-list item a second time.
- Unclear GM rulings are held. Active Plays block new IC messages, including an
  attempted IC clarification. The fixture continues only through explicit
  synthetic human-DM TaskFrame review. A dedicated source-bound OOC intent response
  for the actual actor remains needed; this run does not claim automatic recovery.
- Handler knowledge stays role-scoped, even with the GM and Handler on one human
  account. The private sighting, other role's dossier fears and GM-only motive
  must remain absent from all actual Handler requests and reviewed replies.
- The standard HandlerRequest currently carries question, role-known references
  and addressed updates, not the new dossier. Anchor's wording here is an injected
  fixture persona. A role-filtered dossier/memory bridge is needed before claiming
  dossier-driven model characterization through that transport. Voice consistency
  and repetition here come from templates; compelling characterization and pacing
  still need an independent model/human review.
- Most social messages should remain quiet. Repeated direct Handler questions are
  intentional routing probes, not evidence of good natural intervention pacing.
  Optional Director WAIT reviews reuse existing observation claims and apply no
  dialogue, mechanical effects or automatic world development.

The engine held its boundaries during development. Initial runs stopped at fixture
assumptions: wrong profile type/response enum, a receipt-field mismatch, mandatory
Heat, reused turn-based command keys and already resolved work. These were fixed
in the test harness without weakening native guards or inventing resolved work.

## Reproduction and artifacts

```text
.venv/bin/python tools/playtest_sustained_campaign.py --directory var/p2-sustained-campaign-20261117
```

Use a fresh directory. The full run stores a readable [campaign-transcript.md](../var/p2-sustained-campaign-20261117/campaign-transcript.md),
`campaign-summary.json`, events/snapshots, separate Handler audit packets and
private GM ruling packets. `gm-blind-requests.json` excludes fixture judgments;
use it for a later independent GM review rather than feeding expected verdicts
back to a reviewer. Artifacts and the synthetic ledger stay private under var.
A failure preserves `campaign-partial.json`; it must not be reported as a pass.

Reproduce the independent artifact and length comparison with:

```text
.venv/bin/python tools/audit_sustained_campaign.py --directory var/p2-sustained-campaign-20261117 --baseline var/p2-sustained-smoke8-20261117
```

Its results are saved as `independent-artifact-audit.json`. It validates saved
projections and comparison results, without running a model or changing canon.

The trial runtime now saves its actual scene channel and reopens it, with900 as
the backward-compatible default. Console Play/battle commands follow that channel.
The existing console reopen/owner-confirmation check passed:1test in3.69s,
`var/p2-sustained-console.xml`. Changed-file Ruff lint/format pass for4Python
files, including the new artifact auditor. Registry, retained planning package and repository checks pass. No new full
regression, remote CI, Activity installation or live rollout was performed.

Next: source-bound OOC intent clarification, safe dossier context for actual role
providers, and independent model/human review of the frozen cases. NPC publication
and listener acquisition remain a separate unfinished engine adapter; this test
uses explicitly authored synthetic participant inputs and grants no authority to
speak for real player-owned characters.
