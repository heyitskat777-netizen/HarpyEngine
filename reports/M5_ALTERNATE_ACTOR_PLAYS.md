# Issue 3 — Independent AI Plays for alternate actors

The isolated branch `codex/m5-alternate-actor-plays` starts at
`5f520e95ac09d4db514070890164d56258b38029`. The local development branches,
available origin refs, and source-only Activity package `723955c` do not
contain `girlframe.services.director_play_options.initiative_play_options`.
The proposal contract and Activity projection from the separate AI checkout
are required for integration. The entries below describe the available
engine's native ports and identify which can support that integration.

## Native role and Play checklist

| Role and Play | Native entry and eligibility | Owned follow-up or integration requirement |
| --- | --- | --- |
| NPC · Fan, Patron or Smuggler handover | `NpcHandoverService.menu` and `propose` require the actual owned NPC with the matching job and a living local Girl in the original cast. Patron and Smuggler use an actual eligible carried item. Smuggler also requires the appointed controller in this port. [Service](../src/girlframe/services/m3_npc_handover.py) | The original Girl owns acceptance. The accepted receipt performs the real transfer. This is a candidate for the first NPC initiative adapter. [Native test](../tests/rules/test_npc_job_handover.py) |
| NPC · Intelligence Agent inquiry | `IntelligenceService.menu` and `ask` use the current agent and local, visible NPC subjects in the same cast. The service returns an inquiry ID without spending a Pilot's resources. [Service](../src/girlframe/services/m3_npc_intelligence.py) | The assigned facilitator verifies a supported finding. Only the original agent can read the private finding. This is another candidate for the first NPC adapter. [Native test](../tests/rules/test_npc_intelligence.py) |
| NPC · Guard counter, care, and ordinary Flirt response | Guard procedures and care have separate typed source contracts. The supported ordinary NPC Flirt port starts from a Girl's actual Flirt or another explicit producer. [Guard](../src/girlframe/services/m3_npc_guard.py) · [Care](../src/girlframe/services/m3_npc_care.py) · [Flirt](../src/girlframe/services/m3_npc_flirt.py) | Keep source-bound responses out of the independent picker. A generic free-standing NPC basic Flirt requires a native initiation service for that role. |
| Alternate Harpy · Put Someone Beneath You | `ActorPlayService.preview` and `begin` can use the actual native or converted Harpy reference. The specialized preparation checks the exact target and original body. Roll, Heat and outcomes are sourced from the Harpy. [Service](../src/girlframe/services/m3_actor_plays.py) · [Preparation](../src/girlframe/services/m3_harpy_beneath.py) | The mid-tier native test checks exact receipt replay and preserves the controller's Pilot sheet. This is a candidate for the first Harpy initiative adapter. [Native test](../tests/rules/test_harpy_beneath.py) |
| Alternate Harpy · Flirt, Engage, All Out Assault and Go For the Core | The same native actor entry dispatches specialized paths. The exact body, retained or blocked Plays, target and physical combat eligibility must be checked for each. [Actor service](../src/girlframe/services/m3_actor_plays.py) · [Flirt test](../tests/rules/test_harpy_flirt.py) · [Assault test](../tests/rules/test_harpy_assault.py) | Expose only each separately validated option and preserve current actor-specific outcomes. |
| Alternate Harpy · Keep Your Head, Disobey and paid follow-through | Independent Keep requires its own current trigger and an eligible original actor. Gaze or combat child Keeps and role-specific Disobey need their original parent, Order or encounter. Follow-through requires its exact native source. [Actor service](../src/girlframe/services/m3_actor_plays.py) · [Gaze](../src/girlframe/services/m3_harpy_gaze.py) | Assigned children and paid follow-through remain in the original response flow. Unsupported masked Disobey needs a native route for the scoped Order. |
| Hostile Gorgon · Attack | `GorgonPlayService.preview` and `begin` bind the current original Gorgon, actual owned Assets, target and cast. The native service checks current availability, operational resources, target identity and physical reach. [Service](../src/girlframe/services/m3_gorgon_play.py) | An existing test saves source-bound damage without a fictional Girl roll. The tested interrupt gives Keep Your Head to its original pilot. This is a candidate for the first Gorgon initiative adapter. [Native tests](../tests/rules/test_gorgon_runtime.py) |
| Hostile Gorgon · Collateral Damage, Warp, and Class or Type declarations | `GorgonPlayService` exposes its registered declaration set. Native cases require particular Classes, Types, capabilities, targets, locations, or their existing source event. [Declaration](../src/girlframe/engine/m3_gorgon_play_state.py) · [Service](../src/girlframe/services/m3_gorgon_play.py) | Discover eligibility per declaration. Preserve the original chooser on interrupt, prevention, defense, exposure and other source-bound response effects. |

## Integration contracts to verify

- Resolve `ActorRef`, current controller, original cast and the current encounter
  or turn from engine state. Session Zero ownership, the applicable model scope,
  existing consent and current audience must authorize the role before exposing
  options. Matching a Discord account cannot authorize a different actor's sheet.
- Reuse the existing initiative option and review contracts once their source is
  available. Offer the approved native action shape, targets, reach, resource
  limits and role-owned choices. A reviewer should receive a scoped request and
  a specific missing prerequisite when the native port cannot validate an option.
- Recheck authority and freshness in the native write transaction. The existing
  `OnboardingStore.source_guard` used by approved Handler offers provides a
  transaction guard. Retain a stable native command key per exact approval and
  recover its receipt across restart. A fresh action must validate its current
  mechanical preconditions. An exact replay must still enforce current access.
- The existing Activity projection must consume those options and distinguish
  proposal review, native start, native receipt and pending human-owned work.
  For the three acceptance cases, use a wrong controller, stale actor or turn,
  out-of-reach or forbidden target, human-owned response and exact retry.

## Native target projections

The Harpy native preview now exposes `beneath_targets` using the same known
co-presence check as Put Someone Beneath You. The general `opponents` list
can still contain a distant Girl. The native Discord form uses the restricted
field. A target moving away before submission causes rejection before the
Harpy's Heat changes or a die rolls.

The Gorgon preview now exposes `attack_targets` keyed by the actual Gorgon
and target `ActorRef.token` values. `same_cell` records known physical reach.
`requires_judge` preserves the existing capability and reach decision. The
native confirmation uses the same target checks as the projection and
rejects a concealed target or a target with changed casting. The Gorgon's
actual capability is still chosen from its own Assets. The target's original
controller retains the defense and any resulting response Play.

The Activity handoff's older `PrivateBattlefield` has a turn epoch and cursor
in the canonical scene's `activity_battlefield_turn` fact. Its roster admits
placed Pilot sheets and visible Handler-controlled NPC and Gorgon actors.
It omits alternate Harpies from that turn roster. The current Activity source
is needed to reconcile this limitation, consume the native target fields,
and bind an approved action to the exact turn actor and cursor at submission.

The synthetic native selection passed **16 tests** with 76 deselected. It
included all three NPC handovers, the Harpy reach and original-sheet checks,
and the Gorgon attack and defender checks. Every action used the native
service or native Discord fixture. The final target-only selection passed
**2 tests** in 4.02 seconds with 79 deselected. Ruff lint and scoped typing
also passed. The newer Activity initiative projection
and the AI approval-to-receipt flow remain separate open acceptance checks.

```sh
PYTHONPATH=src python -m pytest -q --tb=short \
  tests/rules/test_npc_job_handover.py tests/rules/test_harpy_beneath.py \
  tests/rules/test_harpy_actor_resources.py tests/rules/test_gorgon_runtime.py \
  -k 'projection or native_harpy_mid or forced_heat_spend_pair or attack or npc_possession'
```

## Baseline evidence

On `5f520e9`, these focused native selections passed using disposable databases.
They establish native behavior before the missing AI integration is reconciled.

```sh
PYTHONPATH=src python -m pytest -q --tb=short \
  tests/rules/test_harpy_actor_resources.py tests/rules/test_gorgon_runtime.py \
  -k 'forced_heat_spend_pair or actual_gorgon_attack_owned_damage or actual_attack_response_child'
# 5 passed, 75 deselected in 10.44s

PYTHONPATH=src python -m pytest -q --tb=short \
  tests/rules/test_npc_intelligence.py tests/rules/test_harpy_beneath.py \
  -k 'intelligence_is_verified or native_harpy_mid'
# 2 passed, 6 deselected in 7.34s

python tools/verify_activity_bundle.py \
  --source /workspace/source-handoff-2026-11-16 \
  --output var/alternate-actor-baseline --p2-routes \
  --test test_reviewed_ai_trial_activity.py
# 1 passed in 9.62s
```

The Activity check exercised the existing scoped review on the synthetic host.
Independent AI selection through native start and receipt remains pending for
all three actor kinds. No provider or running Activity was used.
