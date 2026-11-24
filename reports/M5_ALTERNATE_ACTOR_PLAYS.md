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
| NPC · Patron and Smuggler handovers | Verified in the Activity and native controls. Each offers only the original NPC's eligible held item. The original Girl accepts, and restart recovers the saved offer. Smuggler uses its appointed native controller. [Activity tests](../harpy-activity-lab/test_alternate_initiative.py) · [Native tests](../tests/rules/test_npc_job_handover.py) |
| NPC · Intelligence Agent inquiry | Native service uses an owned Intelligence Agent and visible local subject. The alternate picker needs an inquiry adapter that sends the actual finding to its assigned facilitator and keeps the returned intelligence private to the Agent. [Native service](../src/girlframe/services/m3_npc_intelligence.py) |
| NPC · Guard counter, care and Flirt | Guard, care and ordinary Flirt responses require their typed initiating sources and original response ownership. An independent ordinary NPC Flirt requires a native initiation form. The Activity offers a scoped facilitator referral that records the missing producer. [Guard](../src/girlframe/services/m3_npc_guard.py) · [Care](../src/girlframe/services/m3_npc_care.py) · [Flirt](../src/girlframe/services/m3_npc_flirt.py) |
| Alternate Harpy · Put Someone Beneath You | Verified through Activity generation, owner approval, native start, owned selection, completed native action, and exact restart retry. The action spent the Harpy's own Heat, saved its roll and effects, and preserved the human controller's Pilot sheet. The native projection excluded the remote original Girl. [Activity tests](../harpy-activity-lab/test_alternate_initiative.py) · [Native tests](../tests/rules/test_harpy_beneath.py) |
| Alternate Harpy · Flirt, Engage, All Out Assault and Go For the Core | Native services exist. Each needs a separate adapter to bind the actual eligible trigger, retained Play where applicable, target and combat capability. [Native actor service](../src/girlframe/services/m3_actor_plays.py) |
| Alternate Harpy · Keep Your Head, Disobey and paid follow-through | Independent Keep needs its own current trigger. Gaze or combat children, Orders and paid follow-through belong to their existing sources. Masked Disobey has a scoped facilitator referral for the missing native continuation for its Harpy body and Order. [Actor service](../src/girlframe/services/m3_actor_plays.py) · [Gaze service](../src/girlframe/services/m3_harpy_gaze.py) |
| Hostile Gorgon · Attack | Verified through Activity generation, owner approval, native start, original defender's own damage and Asset choices, and exact restart retry. A Gorgon attack expended no die. Native tests also covered hidden targets, disputed reach or damaged capability, and the original Pilot's assigned response Play. The normal registry gate remains in force. A campaign with explicit Activity specialist approval for `gorgon.gorgon.attack` can use the existing subset approval path. [Activity tests](../harpy-activity-lab/test_alternate_initiative.py) · [Native tests](../tests/rules/test_gorgon_runtime.py) |
| Hostile Gorgon · Attack against an NPC, Harpy or Gorgon | Verified from Activity model proposal through native completion against all three targets. The NPC case resolves through the original engine outcome. A Harpy or Gorgon defender pits their actual Asset, then the assigned judge owns the result. These controls now appear in the owner's Activity desk. A Sprite interception or a resulting Defeat uses its separate native workflow. [Activity tests](../harpy-activity-lab/test_alternate_initiative.py) · [Native tests](../tests/rules/test_gorgon_runtime.py) |
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

## Mixed-cast verification

The expanded suites ran on `6a3de3f` with disposable SQLite campaigns.
The affected Activity tests also ran on the follow-up that adds Patron and
Smuggler handovers and the Gorgon contest controls. The native suites cover
candidate mechanics behind their existing fixture policies and release gates.

| Synthetic selection | Result | Coverage |
| --- | --- | --- |
| `tests/rules/test_npc*.py` and `test_battlefield_attack_parity.py` | 32 passed | Local handovers, care, personal Bonds and Use, Intelligence, Orders and Disobey, source-bound Flirt, ownership and Battlefield assault. |
| `tests/rules/test_harpy*.py` and `tests/rules/test_actor_play*.py` | 148 passed | Original Harpy body and resources, shared Plays and responses, actual NPC Core target, advancements, rest and Defeat. |
| `tests/rules/test_gorgon*.py` | 157 passed | Class and Type mechanics with actual NPC, Harpy and Gorgon targets, defense ownership, Collateral Damage, Warp, Asset contests and source-bound restart. |
| `harpy-activity-lab/test_alternate_initiative.py` on `1ce3ffdf` | 16 passed | Live-path HTTP in the local simulator, three NPC handovers and mixed-cast Gorgon Attack through the private owned controls. |

| `test_sniff_out.py`, `test_leviathan_obsession_flow.py`, `test_journalist.py`, `test_sprite_source.py`, and `test_physiotherapist.py` | 21 passed | Specialist source and interaction cases held outside the role-prefixed files. |
| `test_cast_service.py`, `test_alpha_brutalize.py`, `test_ankou_npc_brutalize_feedback.py`, `test_princess_npc_conversation.py`, `test_pilot_candidate_promotion.py`, and `test_psychologist.py` | 25 passed | Printed NPC job prompts, Guard response, directed discussion, approved promotion, and the Psychologist's owned countermeasures. |

Run the three native selections with the same `PYTHONPATH`, adapter, and
`mission_lab.ENGINE` wrapper documented above. Supply the full listed file
selection without a `-k` expression. Run the synthetic Activity test file
with `python -m pytest -q --tb=short harpy-activity-lab/test_alternate_initiative.py`.

| Interaction | Proven behavior and remaining boundary |
| --- | --- |
| NPC to Girl | Fan, Patron and Smuggler work in the Activity. Intelligence, native care, journalist work, Orders and source-assigned Flirt use their native controls. The handover services require a local, out-of-Frame Girl as the recipient. |
| NPC to Harpy or Gorgon | There is no general NPC attack or voluntary cross-cast handover in the reviewed projection. Guard counters and NPC Flirt stay tied to actual triggering Plays. NPC control transfers do not make another species eligible for a job effect. |
| Harpy to NPC | Native Go For the Core completes against an eligible NPC without taking the controller's Pilot resources. Its independent AI Activity start still needs the actual battle declaration and follow-up form. |
| Harpy to Gorgon or other Harpy | Source-linked Harpy Keep and the Gorgon Asset contest have native outcome evidence. Independent Harpy attack and normal answers outside the tested Activity choices still use the source-specific native controls. |
| Gorgon to NPC, Harpy or Gorgon | Activity Attack completes against all three. The Harpy or Gorgon defender selects their own pitted Assets, and the original adjudicator selects the actual losing Asset. A Sprite interception, assigned counter or resulting Defeat follows its original workflow. Other Gorgon declarations require their typed trigger and an Activity initiative bridge. |

## Alternate actor control and portrayal

The facilitator can prepare an available alternate-role initiative and request
a reviewed draft from the existing Pilot model route. Only the current native
controller can delegate the role, confirm its dossier, approve the draft and
start the native Play. A facilitator can do those steps for an actor they
actually control and can adjudicate an outcome when the native workflow assigns
them that role. The narrower role packet enters generation even when the
facilitator can see more of the world.

NPC, Harpy and Gorgon owners can use **Open alternate actor portrayal** in
the Activity Director work. The approved version carries voice, current drive,
fear, contradiction, limits and contextual reactions. NPC jobs, the actual
Harpy Frame, and Gorgon Class and Types enter generation from the actor's own
engine state. The existing scoped memory and agenda logic supplies approved
motivations and witnessed evidence. Pending drafts and another actor's
portrayal stay outside the prompt. The model can propose or wait, and a
proposal or portrayal edit grants no native Play authority.

### Reviewed Harpy and Gorgon comms

The facilitator can now select **Draft reply** under **Character initiatives**
for an AI-enabled Harpy or Gorgon. This path uses the latest eligible captured
comms and the actor's own approved portrayal. It works without an eligible
native Play. The source must still belong to the current cast and audience
and reach the actor through the engine's communication checks. A private
line, a request addressed to the GM, or a turn claimed by the NPC address
workflow stays outside this path.

The actor's controller sees the heard line and the draft under **AI
contributions**, approves it for specific listeners, then sends it. The
Activity files the exact reply in the selected listeners' transcripts. The
saved receipt recovers after reopening and retries file one copy. A source
edit or withdrawn control before delivery requires a fresh review. An
approved decision to wait closes the turn. HarpyEngine still owns all
native Plays, resources and outcomes.

Unprompted scene initiative and narrative quality in a sustained mixed-cast
session remain separate work. Cross-cast relationships outside the existing
identity projection remain gated. The automated checks use synthetic actors
and stub responses.

The Activity alternate-initiative suite passed 24 tests (76.00 seconds) with
`python -m pytest -q --tb=short harpy-activity-lab/test_alternate_initiative.py`
from this checkout. Five cases cover Harpy and Gorgon dialogue, reopening,
selected-listener visibility, retry, source edits, control revocation and
reviewed waiting. The Gorgon case supplies no native Play projection. Nine
focused shared Director and AI Pilot checks also passed (22.23 seconds).
Ruff, mypy, JavaScript syntax and patch whitespace checks passed.

The Activity suite at `b70383b` passed 19 tests (49.33 seconds). Its three portrayal
cases verify the approved voice, drive, and source-backed role identity after
restart, a rejected edit from another controller, and exclusion of unpublished
drafts before model generation. Nine focused Director, dossier, Pilot
initiative and Play catalog checks passed (108 deselected, 10.64 seconds).
Scoped Ruff, mypy, JavaScript syntax and patch whitespace checks passed.
These runs exclude the full repository regression and authenticated Discord.

```sh
python -m pytest -q --tb=short \
  tests/rules/test_{sniff_out,leviathan_obsession_flow,journalist,sprite_source,physiotherapist}.py
python -m pytest -q --tb=short \
  tests/rules/test_{cast_service,alpha_brutalize,ankou_npc_brutalize_feedback,princess_npc_conversation,pilot_candidate_promotion,psychologist}.py
python -m pytest -q --tb=short \
  tests/test_{director_initiative,director_dossiers,director_reactions}.py \
  tests/test_native_ai_pilot_initiative.py harpy-activity-lab/test_play_catalog.py \
  -k 'initiative or controller_confirmation or npc_and_pilot or generated_pilot_uses or sheet_experiences or reuse_a_human or delivery or npc_reaction'
```
