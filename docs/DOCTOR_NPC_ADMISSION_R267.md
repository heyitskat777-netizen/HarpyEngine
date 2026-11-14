# Doctor NPC Nanobot admission: r267 bounded correction

## Finding and source

Reopened the authorized `Girl Frame 2026_09_01 (1).pdf`, PDF pages 71–73, including printed p70 Nanobot Injection. Low requires an Asset repair; mid requires the amount of Heat spent and 1–2 selected benefits; high requires five Heat and two benefits. These are mechanical outcomes, not merely GM choices. The rule does not establish an NPC resource sheet or authorize substituting its controller's resources.

Recovered r266 `services/m3_doctor.py` admitted a physically reachable NPC, charged the Doctor, and rolled. Its NPC result recorded `printed_gain` with `applied_gain=0, resource=None`; mid could remove an effect and finish despite missing the mandatory Heat. Low/high could become known unsupported pending work. Existing tests proved these partial paths, not successful printed treatment. The restricted-test exclusion documented in r262 was not enforced at new-action admission.

## Change

A shared `require_nanobot_patient` admission check rejects new NPC Nanobot attempts before roll/cost/scene-lock changes and excludes those NPCs from the Nanobot menu. Original NPC body/contact validation runs first, retaining more specific rejection for impossible patients. The check is not used by recovery of existing actions. Other Doctor NPC care and Here for Support admission, and Pilot Nanobot treatment, remain unchanged.

This is a **playtest safety exclusion, not completion of NPC medical mechanics**. A human GM may resolve fiction but cannot certify absent repairs, Heat or Identity changes. NPC Nanobot remains unsupported until an actual rules-backed resource/outcome port exists for every random result. No registry approval, release gate or deployed state changed.

## Authored verification

- `test_doctor_npc_admission.py`: actual reachable NPC excluded from new Nanobot selection, remains in other-care target inventory, native Nanobot remains listed; direct admission rejected with no new dice, state, pending action or scene-lock mutation.
- Existing `test_doctor_npc_nanobot.py` helper now explicitly seeds *legacy pre-r267* actions by temporarily mocking only the new admission check. It restores the gate before any continuations. Historical GM-bridge and effect-removal tests thus retain their purpose without claiming new NPC treatment works. Historical mid completion is still deficient; this patch does not retroactively invent its missing Heat or migrate past events.
- Python compileall passed for three changed Python files. Worker did **not** run pytest; root should record actual focused results separately. Suggested minimum: new admission test and historical high-result GM bridge.

No full regression, live Discord, all-type certification, migration or restoration claim. Isolated source only; bot off, no merge/deploy.

Independent review found stale native form instructions still advertising NPC mid-result removal. Corrected `discord_adapter/m3_doctor.py` to state new NPC Nanobot is unavailable while historical pending choices remain recoverable, and added a native form instruction assertion to the focused admission test. No worker pytest run.
