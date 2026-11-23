# Independent AI Plays for alternate actors

The development branch `codex/activity-alternate-play-initiative` starts at
the verified Activity parity commit `4f6e487841f4504b8387dd370f65f514f3a59932`.
It carries the earlier native audit and target fixes as `373749e` and
`0f115b0`. The parity branch supplied the Activity host, native Play
projection, Director initiative queue, and owner review. This work adds
alternate actor eligibility, review handoff, and native receipt recovery to
those paths.

## Role and Play checklist

| Role and Play | Status and evidence |
| --- | --- |
| NPC · Fan handover | Verified through Activity generation, owner approval and native proposal. The original Girl accepted and transferred her actual carried item. Another controller could neither read nor answer her offer. Exact restart retry recovered the original receipt. [Activity tests](../harpy-activity-lab/test_alternate_initiative.py) · [Native service](../src/girlframe/services/m3_npc_handover.py) |
| NPC · Patron and Smuggler handovers | Native original-item and original-recipient tests passed. An independent initiative form must offer the NPC's eligible held items. Smuggler also needs its appointed authorized controller. [Native tests](../tests/rules/test_npc_job_handover.py) |
| NPC · Intelligence Agent inquiry | Native service uses an owned Intelligence Agent and visible local subject. The alternate picker needs an inquiry adapter that sends the actual finding to its assigned facilitator and keeps the returned intelligence private to the Agent. [Native service](../src/girlframe/services/m3_npc_intelligence.py) |
| NPC · Guard counter, care and Flirt | Guard, care and ordinary Flirt responses require their typed initiating sources and original response ownership. An independent ordinary NPC Flirt requires a native initiation form. The Activity offers a scoped facilitator referral that records the missing producer. [Guard](../src/girlframe/services/m3_npc_guard.py) · [Care](../src/girlframe/services/m3_npc_care.py) · [Flirt](../src/girlframe/services/m3_npc_flirt.py) |
| Alternate Harpy · Put Someone Beneath You | Verified through Activity generation, owner approval, native start, owned selection, completed native action, and exact restart retry. The action spent the Harpy's own Heat, saved its roll and effects, and preserved the human controller's Pilot sheet. The native projection excluded the remote original Girl. [Activity tests](../harpy-activity-lab/test_alternate_initiative.py) · [Native tests](../tests/rules/test_harpy_beneath.py) |
| Alternate Harpy · Flirt, Engage, All Out Assault and Go For the Core | Native services exist. Each needs a separate adapter to bind the actual eligible trigger, retained Play where applicable, target and combat capability. [Native actor service](../src/girlframe/services/m3_actor_plays.py) |
| Alternate Harpy · Keep Your Head, Disobey and paid follow-through | Independent Keep needs its own current trigger. Gaze or combat children, Orders and paid follow-through belong to their existing sources. Masked Disobey has a scoped facilitator referral for the missing native continuation for its Harpy body and Order. [Actor service](../src/girlframe/services/m3_actor_plays.py) · [Gaze service](../src/girlframe/services/m3_harpy_gaze.py) |
| Hostile Gorgon · Attack | Verified through Activity generation, owner approval, native start, original defender's own damage and Asset choices, and exact restart retry. A Gorgon attack expended no die. Native tests also covered hidden targets, disputed reach or damaged capability, and the original Pilot's assigned response Play. The normal registry gate remains in force. A campaign with explicit Activity specialist approval for `gorgon.gorgon.attack` can use the existing subset approval path. [Activity tests](../harpy-activity-lab/test_alternate_initiative.py) · [Native tests](../tests/rules/test_gorgon_runtime.py) |
| Hostile Gorgon · Collateral Damage, Warp, and Class or Type declarations | The native entry requires actual Class, Type, capability, location, target or original source as applicable. Collateral Damage has a scoped referral for the missing site, capability and response binding. Other declarations need per-Play projection and continuation evidence. [Native declaration](../src/girlframe/engine/m3_gorgon_play_state.py) · [Native service](../src/girlframe/services/m3_gorgon_play.py) |

## Authority and Activity handoff

- The actual original cast controller enables AI initiative for a single
  `ActorRef` in that scene. The grant records controller and cast source in the
  existing append-only audit. Its latest event and current scene consent are
  checked at submission. Joining a different cast or assigning a new
  controller invalidates the old grant. The projection uses the actor's own
  role and resources.
- The existing facilitator `scene-initiative` list exposes the exact
  engine-generated Play and target to the nominated model after authorization.
  The provider sees a role-filtered packet and the choice ID, label and reach
  status. Costs, fingerprints and native choice bindings stay internal. The
  existing owner review displays the projected target and the choices that
  the human controller has to complete. A proposal or its approval leaves
  rules, rolls and game state with the engine.
- `scene-alternate-start` checks the saved exact proposal, live consent,
  current controller, cast, target, native preview and battlefield turn
  inside the native transaction. One native start is allowed per actor
  per delegated scene in free play, or per actual turn when a battlefield
  order is active. The saved native command is the receipt, and identical
  retries recheck access and recover it without a second roll or cost.
- The Activity renders the scene's owned controls and Play confirmation in
  the existing Director desk. Its `scene-alternate-actors` projection includes
  each current Play and eligible target, reach status, native costs and required
  selections for the original controller. It reads `scene-alternate-handovers`
  and `scene-alternate-choices` for owned follow-ups and sends the
  stable approval or choice ID back with the required native fields. The
  response routes preserve their original chooser. Starts with additional
  specialized responses keep those existing native controls. No separate
  scheduler, schema migration or model endpoint is required.
- A campaign needs an approved opening, its existing AI observation consent,
  and a configured model route to generate live proposals. The Gorgon
  candidate needs approved Activity specialist access while its independent
  review is pending. Unsupported work can be sent to the assigned
  facilitator with the precise source prerequisite and a scoped receipt.

## Verification

The commands below use temporary synthetic databases. The three HTTP cases
run the actual local Activity server with synthetic signed-in cookies and
stubbed model outputs. The direct adapter cases continue through owned
native decisions and reopen the database before retrying each start.
The second command points the older lab fixtures at this checkout so
they use its rules registry and engine source.

```sh
export PYTHONPATH=src:tests:tests/rules:harpy-activity-lab
export HARPY_ACTIVITY_TEST_ADAPTER="$PWD/harpy-activity-lab/p2_scene.py"

python -m pytest -q --tb=short harpy-activity-lab/test_alternate_initiative.py \
  tests/test_director_initiative.py tests/test_native_ai_pilot_initiative.py \
  harpy-activity-lab/test_play_catalog.py -k 'initiative or reuse_a_human'

python -c 'from pathlib import Path; import mission_lab, pytest; mission_lab.ENGINE = Path.cwd(); raise SystemExit(pytest.main())' \
  -q --tb=short tests/rules/test_npc_job_handover.py \
  tests/rules/test_harpy_beneath.py tests/rules/test_harpy_actor_resources.py \
  tests/rules/test_gorgon_runtime.py harpy-activity-lab/test_ai_native_plays.py \
  -k 'actual_npc_possession or harpy_beneath_projection or native_harpy_mid or forced_heat_spend_pair or actual_gorgon_attack_owned_damage or attack_projection or actual_attack_response_child or native_actual_owner_declines_damaged_capability or projection_matches_owned_native_scene_controls or unsupported_batch_only_files'
```

The initiative selection passed **16 tests** with 95 deselected. The affected
native and Activity selection passed **14 tests** with 108 deselected. Scoped
Ruff, five-file mypy, JavaScript syntax and patch whitespace checks passed.

The parity handoff's 99 focused checks and legacy JANUS enrollment failure are
historical. The current verification covers the alternate initiative and
affected native paths. Full regression, browser interaction on the real
Discord Activity, paid provider validation, and real-player acceptance
remain separate.
