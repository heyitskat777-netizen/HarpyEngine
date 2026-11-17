# P2 Living Campaign and Character Agency

Implementation: **94f4d1effaa05def2ccc94f6e49d11b3606cdccd**, based on
f3c4b3b and the retained worldbuilding/knowledge/GM-outcome work. This is an
**offline proposal and review foundation within P2**. M0–M7 and P1–P3 are unchanged.
No original cast/campaign was imported, provider installed, money spent, campaign
changed, Discord connection made or runtime deployed.

## Review and integration decisions

The work order fits the existing Director. Native world developments already hold
established details and goals; scoped disclosures already distinguish knowledge
from GM-only information. Native Play consumers and original owners still decide
mechanics. New records attach to these authorities instead of copying them into
a second plot engine.

| Work package | Implemented behavior |
|---|---|
| Dossiers | Append-only accepted versions on native ActorRef/incarnation; background and recurring forms share identity. Stable behavioral profile and changing controller-authored perspectives are separate. Goal/resource IDs reference existing sources. |
| Private/public views | GM notes are a separate record family. Actor self packets exclude those notes and other actors' sheets. Personnel returns explicitly published summary/mannerisms only after native identity visibility checks. |
| Ownership | GM may propose a player dossier; its actual controller confirms. Controller replacement requires an explicit new self-sheet and cannot inspect old private reaction drafts, even after renewed casting. |
| Fronts | Evidence-backed participants, competing intentions, hypotheses, possible moves, consequences, deadlines and optional attention clock. Accepted native outcomes or explicit fictional-time events support revisions; resolving requires a native outcome. |
| Attention | Full clocks and elapsed fictional deadlines mark readiness without disaster, resource loss or automatic outcome. Each underlying native action can advance a particular Front only once, regardless of alternate narration receipts. |
| Role packets | Reactions receive actor-known speech, memories, self dossier and flat already-known Front fragments. Private Front titles, grouping, clocks, hypotheses and GM notes never enter the actor packet. |
| Reactions | WAIT, refusal, compromise, delay, natural NPC dialogue, optional scene invitations and links to existing native work. NPC controller review is required; Pilot speech is rejected. Handler speech keeps its existing engine RESPOND/WAIT and reviewed-delivery workflow. |
| Scheduling | Real observation claims/leases and the existing quiet window are reused. A reviewed WAIT can complete the frozen batch without a message. Explicit GM review may run without a claim. No new scheduler or between-input advancement was installed. |
| Ensemble | A GM review surface exposes current dossiers, review counts, last reviewed source and private Fronts. It suggests considering neglected opportunities without a required appearance or clock advance. |
| UI preparation | Session work exposes metadata-only dossier/reaction work and GM-only ready Fronts; the consolidated Activity handoff describes controls and boundaries. |

Intentions, beliefs and relationship perspectives are labelled as such. They do
not establish facts, alter Bonds, spend resources, determine dice or compel a
player. Natural NPC prose stays a private reviewed candidate. Approving it does
not publish speech or teach listeners. REQUEST_ACTION validates actual pending
work again at approval; execution still belongs to its original native service.
Scene offers do not move characters or create accepted scenes.

## Sustained fixture rehearsal

```text
.venv/bin/python tools/playtest_living_campaign.py --directory var/p2-living-campaign-20261117
```

The run uses a fresh native archive clerk, explicit NPC/Handler casting, two
actor dossiers and the retained 112-input scene framework. Background-to-recurring
promotion retains the clerk's identity and changes state explicitly. The private
clerk objective is disclosed to that NPC alone; neither Handler nor the human's
other role inherits it.

| Evidence | Result |
|---|---|
| Player inputs / role-projection audit groups | **112 / 112** |
| Private GM/Front canaries or unreported enemy sighting leaked | **0 detected** |
| Controller-reviewed NPC candidates | **7**: refusal1, compromise1, delay1, WAIT2, scene offer1, dialogue1 |
| Attention branches | Aversion: dormant0/2; redirection: active1/2; quiet deferral: ready0/2 after explicit deadline3 |
| Mechanical state | Native state excluding narrative facts/revision preserved after every input; **0 rolls**, no resource/Bond/mission changes |
| Restart/retries | NPC dossier version2 persists after database reopen; confirmation/input/reaction retries do not duplicate accepted work |
| Spending | **0 external tokens / cost** |

Example private candidates include a refusal to share a private ledger with an
offer to discuss the public index, a compromise limited to public records, a
request to defer, and an optional later conversation the player may decline.
WAIT returns no text. These demonstrate supported response forms and scope;
the selected prose/turns are handwritten fixtures, not autonomous model choices.
The three branch changes are explicit GM attention reviews supported by fictional
time, **not proof that a delivered conversation resolved a native conflict**.

Artifacts remain private under `var/p2-living-campaign-20261117/`:
`living-summary.json`, `living-results.json`, `living-role-packets.json` and the
synthetic ledger. Each stored audit group contains separate NPC and Handler
projections for verification; split them before any role-model review. Do not
feed paired audit packets to a fictional role.

The separate unchanged worldbuilding rehearsal was also rerun into
`var/p2-living-world-regression-20261117/`: **112 inputs, 3 native Plays/rolls,
7 world commitments, 3 selected disclosures, 13 Handler interventions,
112 checked Handler prompts, no pending choices, duplicate world writes or
rerolls**. Those are separate runs and evidence, not one combined live campaign.
The new agency run deliberately preserves mechanics; native-outcome Front
resolution is additionally covered by focused service tests.

## Verification

On frozen implementation **94f4d1e**:

```text
.venv/bin/pytest -q tests/test_director_dossiers.py tests/test_director_fronts.py tests/test_director_reactions.py tests/test_director_reaction_transfer.py tests/test_director_session.py tests/test_director_conversation.py tests/test_director_worldbuilding.py tests/test_knowledge_contract_revision.py --junitxml=var/p2-living-campaign-frozen.xml
39 passed in 35.21s
```

Changed-file Ruff lint/format pass for **13 Python files**; mypy passes **8 source
files**. Registry checks, original planning contracts, offline CLI help/health,
repository manifest/credential scan and `git diff --check` pass. Four new test
files are included in focused CI. No remote CI or full regression was run.

Review caught and fixed old-controller draft access after NPC transfer, a stale
native-work routing gap and metadata recovery when dossier sources need
reconciliation. Development also caught strict JSON tuple decoding and native
casting fixture errors; corrected without weakening cast or role guards. Earlier
14-case and narrow correction runs overlap the final39 and are not additive.
The sustained agency rehearsal preceded the last metadata-recovery hardening;
that recovery case and all affected tests passed on the frozen source.

## Findings and next work

The structural boundaries hold in these fixtures: characters can refuse or wait,
uncertainty remains unresolved, private agendas stay private and attention does
not force outcomes. Human storytelling acceptance remains open. A single clerk
with fixture-selected responses cannot establish ensemble variety, model
initiative, compelling dialogue or pacing over a long campaign.

Next engine work is a source-bound NPC contribution/disclosure adapter: explicit
GM semantic review plus controller approval, frozen recipients, safe publication
receipts and attribution-preserving listener knowledge. Current private replies
must not be copied straight into a public transcript. Then extend the rehearsal
to several independent NPC goals and independently review reaction choices and
quiet periods. Human review should assess recognizable voices, understandable
changes of plan and whether players can avert or redirect an actual conflict.

The [consolidated Activity handoff](../integrations/activity/P2_SESSION_UI_HANDOFF.md)
contains the later UI contract. Model spending, connected Activity behavior,
live campaign changes and deployment remain separate decisions.
