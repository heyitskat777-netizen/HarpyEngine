# Four-part engine continuation and review

The four bounded workstreams in `docs/work_orders/P2_CONNECTED_CAMPAIGN.md`
are complete as an offline, assisted candidate. This increment builds on source
`7243aeb3285b52c22fe8056e18e6122355cc2a6c`; it does not certify the entire rules
catalogue, install an AI provider or connect the Activity UI.
Implemented source and tests are committed as `5f315a4`; the accompanying
documentation records the checks and deferred Activity work separately.

## What is complete

| Workstream | Result |
|---|---|
| Native consequence and recovery | Reused actual damage → owned Defeat → destruction → next-period required work → Pilot replacement preferences → Handler package → Pilot installation. The connected test reopens the database before installation, retries the exact original installation payload, preserves the character/resources/Identities and uses the installed Enforcer in a subsequent real Keep. Existing native reducers remain authoritative. |
| Contextual GM support and ownership | The session work list now labels each pending choice with its effective native decision owner and `typed_outcome` or `native_owner`. A private `decision_context` joins the pending choice, actual source action, current references and canonical GM state. Existing typed adapters handle discretionary rulings; remaining personal/source choices retain native ownership. This adds review context, not a universal execution endpoint or new consumers for every referral. |
| Handler initiative | Explicitly assigned `briefing`, `tactical` and `debrief` references can trigger RESPOND on the next processed input. Pending updates drain in chronology order. Successful saved replies suppress repeats, including carried references for the same Handler and roster; failed generation does not. Direct questions and existing scope warnings retain priority. Private Pilot-only information stays outside the Handler request. |
| Continuity and connected trial | Explicit GM selection carries source-bound references from the preceding closed scene into the next open scene with the same roster. The service preserves known-by actors, claims versus confirmed outcomes, dependencies and immutable root provenance, and checks both context revisions, consent and current actor identity. The trial uses three native scenes in one persisted campaign. |

The GM trial assessment is fixture-authored: maintaining control supports precise
calibration; the native are/are-not traits and declared goal are supplied through
the typed Keep packet. The proposal leaves the action pending until its actual
Handler owner confirms. The engine applies the native result once. This is not
an engine keyword verdict or an evaluation of a real language model.

## Connected trial findings

The confrontation executes native damage and Defeat. Its confirmed GM readback
is explicitly assigned as Handler/Pilot debrief knowledge. The workshop receives
that memory and private Pilot notes, then installs the replacement through the
real source owners. A tactical installation report produces one Handler update.
The Pilot calls Keep to hold a calibration needle steady; the contextual GM
proposal is confirmed by the original Handler owner. The hallway receives the
committed readback and prior knowledge. Handler context contains the outcome,
excluding the Pilot's private notes and the GM's private reasoning.

Review during implementation found and corrected three integration problems:

- Pilots can join only one active native scene. Handoff therefore supports an
  actual closed source scene, rather than requiring simultaneous membership.
- Copying an already delivered debrief initially repeated it in the next scene.
  Delivery suppression now uses original reference identity, Handler identity and
  roster, so copying knowledge does not automatically create a new announcement.
- Withdrawal of original-scene consent blocks carried context. A metadata-only
  archival review now permits retiring the blocked copy and its dependents without
  reading or generating from withdrawn text. Retirement remains append-only.

The native Off-Duty preparation remains open for its actual Strain/period work.
The replacement chain is complete, but the test does **not** claim a completed
Off-Duty period, accepted mission, earned payment or whole campaign lifecycle.

## Local verification

- Integrated development selection: **86 passed in 84.48s**, zero failures,
  errors or skips (`var/p2-connected-candidate.xml`). This preceded the final
  cross-scene delivery suppression and stale-reference retirement adjustments.
- Final affected selection after those adjustments: **19 passed in 23.73s**,
  zero failures, errors or skips (`var/p2-connected-final.xml`). It includes the
  new connected campaign and continuity cases, existing memory, conversation and
  session workflows. These are overlapping runs, not 105 distinct cases.
- Global Ruff lint/format and mypy pass: 2,051 Python files formatted and 956
  source files typed. Runtime registry and original planning contracts pass.
  Offline CLI health passes with Discord disconnected. Repository check has zero
  findings. No rules registry or release approval changed.
- The generated synthetic trace is `var/p2-connected-campaign.json`.
  Reproduce the connected scenario with
  `.venv/bin/pytest -q tests/rules/test_p2_connected_campaign.py`.

No new full regression or Activity adapter run was performed. The earlier
3,475-case engine and 65-case Activity results remain attached to their earlier
source snapshot. The existing integration ZIP likewise remains the earlier
candidate. Local results are not remote CI or human acceptance.

## Review: what to do next

1. Extend this persisted rehearsal through an actual mission acceptance,
   completion/reward, all required Strain/Off-Duty work and next mission. Reuse
   the native lifecycle services and surface their actual blockers. This is the
   next highest-value engine integration exercise; the current trial deliberately
   stops at replacement and a usable subsequent Play.
2. Consolidate Activity ports for the session work list, private GM packets,
   source-owner confirmation, Handler delivery indicators, continuity selection
   and stale-reference retirement. Updated contracts are recorded in the engine
   handoff; authentication, client controls and end-to-end Activity acceptance
   still need implementation in that project.
3. Run a short facilitated human trial for narrative quality and pacing. The
   synthetic Handler is intentionally bounded and template-based. Updates require
   explicit source assignment; native state changes do not automatically grant
   knowledge or trigger an installed background worker. Different-roster disclosure,
   automatic summaries/forgetting and autonomous GM judgment remain outside this
   increment. Conditional fact bridges such as later poor-advice evidence and
   broader all-type branch review remain visible backlog items.

No spending, external model calls, real transcript capture, deployment, bot
restart, live campaign mutation or public message delivery occurred.
