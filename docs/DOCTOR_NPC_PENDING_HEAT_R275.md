# r275: legacy NPC Nanobot removal does not falsely complete treatment

New NPC Nanobot attempts remain excluded before roll (r267). This bounded correction applies to already-rolled legacy mid results only; it does not implement NPC resource sheets.

The retained printed p70/p13 source review in `DOCTOR_NPC_ADMISSION_R267.md` establishes mandatory mid Heat equal to actual expenditure. The prior continuation removed a real selected effect with its controller's confirmation, then completed while its own `npc_heat` recorded a positive printed award and zero applied gain. That is not successful treatment.

After the same real owned removal, a positive unfulfilled Heat award now leaves a new original-patient-owned `doctor_patient` decision carrying an explicit unsupported reason. Existing private facilitator routing exposes the outstanding mechanical requirement without fabricating a resource or repeating the removal. Zero-spend mid results have no outstanding Heat and keep the existing supported removal completion. No past completed events are rewritten, and no NPC controller's Pilot sheet is used as a proxy.

Authored focused verification parameterizes the existing real Dose→Nanobot test with actual zero/one expenditure. The positive case asserts real removal once, other drug effects preserved, mandatory work and private facilitator route, original receipt and no extra dice/cost. The zero case preserves actual scene expiry coverage. The Stim recovery/expiry fixture likewise explicitly uses zero expenditure, so it does not claim a positive award was delivered. Worker did not run pytest; root records actual outcomes. No rule approvals changed; no migration of completed legacy actions, full regression or live Discord claim.

Root focused result: 2 passed in 9.16s. Initial 2 failed in 8.41s were fixture errors: zero-Heat raw dice produced low instead of mid; mock interaction channel ID was unspecified. Both corrected without weakening guards. Separate edited Stim zero-Heat expiry fixture is authored but not rerun. Scoped lint/format passed.
