# ANKOU Processor Core ordinary consequences: r268

## Baseline and scope

Reviewed against recovered r267/v36 source, archive SHA-256
`c363f887b8f71013b54af35ff9fee886041fbc63bb38abf50b0253cee6916257`.
Authorized retained `Girl Frame 2026_09_01 (1).pdf` was reopened with
`pdftotext -f 84 -l 87`; Processor Core is printed p84 / PDF86.
This is a bounded text-level rules/source comparison, not whole-ANKOU approval.
The first root focused run exposed a genuine normal-path production defect: the
shared `ChoiceAnswer` validator requires distinct options, so selecting the printed
repeatable Identity benefit failed before reaching the Ankou consumer. Root run1:
1 failed in 5.06s, preserved as `ankou-run1.log`.

## Printed branch and actual consumer

- **Admission:** `services/m3_ankou_support.py:processor_minds` excludes Handler
  and Gorgons, and honors the optional Cadre and one other person exemptions.
  `services/m3_ankou.py` preparation/validation re-proves original cast, bodies,
  locations and exempt selection before dice. This is not arbitrary NPC food or
  a synthetic actor substitute.
- **Mid:** `m3_ankou.py:apply_choice` requires exactly two benefits. Low requires
  one, high three. Duplicate champion/eyes/will are rejected; repeated Identity
  benefits are explicitly accepted, as printed.
- **Identity benefit:** each selected instance erases an actual eligible original
  Identity, unmarks a different actual marked Identity, and adds the owner's
  selected 1–3 Heat through the resource adapter. Required resource changes are
  not replaced by GM text. Protected/paired/AM-limiter, sedation and applicable
  locked resources remain guarded; not a blanket permission to erase them.
- **Other benefits:** champion uses an attributed real Tag; eyes/will install
  actual temporary Assets with existing cap/replacement checks. Their source IDs
  are persisted in the Processor record.
- **Low/high symptoms:** after benefits, the original owner must select one/two
  distinct printed symptoms. Actual linked recipients receive attributed Tags;
  source completion waits for that selection. Mid does not invent symptoms.
- **Unlink:** actual original owner ends a completed link. Temporary benefits are
  removed through the existing unlink adapter; Identity/Heat changes are not
  fictional reversible bonuses. Symptom Tags survive unlink. `off_duty_start`
  ends symptoms at the source Ankou's next Off-Duty, tracking actual holder via
  `m3_ankou_symptom_expiry.holder` rather than claiming recipient Off-Duty clears
  them. This is observed implementation behavior; the printed timing interpretation remains unsettled. These lifecycle branches were read, not newly runtime-proven here.
- **Native choices:** `discord_adapter/m3_ankou.py:open_choice` offers separate
  benefit/erase/unmark/Heat controls for every printed result slot. It forwards
  only the controls belonging to the selected benefit. Owner-bound service
  validation remains authoritative.

## Bounded production correction

The Ankou native adapter now encodes later repeated Identity selections as distinct
slot-bound `identity_repeat_N` wire tokens. Only the Ankou service decodes these,
and only at that exact slot with a preceding Identity selection. All other invalid
benefits still reject. Stored Processor benefits remain canonical `identity` values.
The global distinct-choice validator is unchanged; other Plays cannot gain duplicate
choices through this correction. No resource, owner, count, or protected-Identity
guard was removed. Files changed: `src/girlframe/discord_adapter/m3_ankou.py` and
`src/girlframe/services/m3_ankou.py`.

## New authored normal-path evidence

`tests/rules/test_ankou_repeated_identity.py::test_mid_processor_repeated_identity_results_survive_unlink`
adds the previously uncovered ordinary repeated-Identity mid branch: real
Processor purchase/proposal/roll, original owner's native result callback,
two distinct erasures and two unmarks, both chosen Heat gains less real roll cost,
then actual unlink with durable Identity/Heat results retained. It also checks
no fabricated Tag/Asset/symptom and untouched processor recipient Identities.

The fixture explicitly synthesizes starting Identity marks and inherits existing
synthetic scene/world/approval setup; choices are directly inserted into the mock
native form. This is not live Discord, actual AI Director, production-rule
approval, all possible beneficiary types, restart/restore or privacy certification.
The worker did not run pytest. Root must record any exact focused execution
separately; authored assertions are not a passing result.

## Playtest impact

The original source-only inspection missed the shared answer-validator boundary;
the failed real native callback established the blocker and justifies this bounded
encoding fix. It does not warrant widening unrelated Processor mechanics.
The repeated benefit is a normal printed result, not a speculative role matrix.
A passing focused test would close only this branch's evidence gap, not clear the
production registry gate or certify every ANKOU Play. Unsupported combinations,
per-type audit work, authorized pre-pause reconciliation and exact final-candidate
release checks remain pending. Bot stays off; no merge/deploy occurred.
