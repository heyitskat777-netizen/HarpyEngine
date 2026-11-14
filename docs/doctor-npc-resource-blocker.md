# r262 Doctor NPC Nanobot mechanical outcome review

Baseline: r261 full source, native Space v30, archive SHA-256 `1f1695d429bf7b46bb1e940b05122588176e12cfb3decf445939a86574edee58`. Read-only investigation; no production code or tests changed or run.

## Source-backed result

Printed Girl Frame 2026-09-01 p70 / PDF72 says mid Nanobot Injection selects 1–2 benefits, high selects 2, and low undamages an Asset. The three benefits are repair 2 Assets, remove an effect, and unmark an Identity. High additionally grants 5 Heat. Two different removable effects are not two different printed benefit selections.

Printed p13 / PDF15 is important: ordinary NPC Asset damage is replaced by attacker-owned injury/Tag, taking/moving/advantage, or death. It does not specify an inverse “repair an NPC Asset” operation, and does not grant NPCs a normal Asset inventory. Therefore simply converting Nanobot repair into removing a second Tag, undoing movement/theft, or resurrecting a dead NPC would invent rules.

`engine/m3_world_state.py:176–201` defines ordinary NPCs with Tags and Bonds but no Asset, Identity, or Heat pool. `engine/m3_battle_state.py:NpcDamage` and `services/m3_battle_npc.py` preserve source-owned replacement damage outcomes; they are not damaged Assets available for undamaging. `services/m3_doctor_npc.py` implements actual Tag / explicit Helpless / supported Stim-effect removal on the original NPC, not its human controller's sheet.

Current `services/m3_doctor.py:232–253` correctly retains unsupported low/high results pending. Its mid branch can offer actual removal, then the original controller confirms it in `doctor_patient`. The existing campaign ruling `doctor-npc-nanobot-real-removal` explicitly prohibits empty repair/Identity choices and two removals completing high. It records NPC Heat as unapplied source metadata rather than inventing a pool. The r259 private GM request is already present and does not settle treatment.

## Classification and shortest safe path

- Doctor → actual Pilot Nanobot: implemented; this review does not establish new test coverage.
- Doctor → NPC mid actual removable effect: implemented with prior focused evidence, not newly tested here.
- Doctor → NPC low/high: unsupported mechanical resource outcome, **not** merely missing UI or a GM-choice handoff.
- Restricted session: disclose exclusion of **all NPC-target Nanobot attempts**, not just high outcomes, because players cannot choose their random tier in advance. Preserve other supported Doctor Plays and Pilot-target Nanobots. This is a candidate test restriction, not completion or all-type certification.
- Any already-rolled NPC low/high attempt must retain original cost, receipt, pending consequence and durable GM request; do not reroll, quietly refund, or mark complete.
- General support requires an explicit source-backed interpretation for ordinary NPC repair/Identity/Heat and an authoritative represented outcome, with original actor ownership, provenance and recovery. No safe narrow change supplies the missing second distinct benefit today.

Existing regression evidence to retain: `tests/rules/test_doctor_npc_nanobot.py::test_npc_nanobot_high_keeps_original_cost_and_result_pending_without_fake_resources` and `tests/rules/test_doctor_npc_gm_bridge.py::test_high_npc_nanobot_opens_durable_gm_request_without_completing_treatment`. No duplicate test added for unchanged behavior; no pytest run.
