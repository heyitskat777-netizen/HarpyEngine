# M3D — Strict Regulations and source-bound breaches

Status: implemented offline within RULES_SUBSET. Independent review and human
acceptance remain pending. This does not complete discipline, careers or M3.

Book PDF 17 / printed p.15 permits an inflictor-defined behavioural rule, optional
disclosure and further Punishment on breach. Book PDF 18 / printed p.16 requires
Handler consultation when a Girl inflicts a Moderate Punishment. The existing
owner ruling assigns unspecified details to the inflictor. The new delegated
`regulation_breach_review` recommendation is recorded in the central ruling register
and machine registry, with alternatives/change impact and clarity-review status.

A typed regulation records the actual Girl incarnation, inflictor, informed
Handler, private text, disclosure choice and imposition source event. It is outside
the Pilot sheet so a concealed rule does not leak through the owner's raw saved
sheet. A private current-rule view enforces actual character/role knowledge.
The Handler's Moderate approval includes both the exact text and disclosure choice;
the subject's consultation projection conceals the text when appropriate.

Only the actual informed Handler records a breach. It requires an explicit human
factual account; no passive transcript or AI infers one. The source event, private
account and separate discipline cause commit atomically. The Handler chooses a
real current mission/Off-Duty context or next Off-Duty. Every occurrence retains
its own cause, outside the approved failure/Dog overlap. Future-period deferral
preserves current recovery, survives restart/rebuild and creates required work
only at the next actual period. It cannot move to a replacement character.

`/mission discipline` includes the rule and disclosure controls, plus exact
consultation. `/mission regulations` lists rules actually known to the caller and
lets the informed Handler record an occurrence with a due-context selector. Saved
breach discipline uses the existing owner-bound inbox/Punishment workflow. No new
command waives required work, chooses the Punishment for a human or discloses
unrelated private rules. Safety, game/row revisions, restored chat and scoped M3
release approval are enforced before mutation.

Acceptance tests: `tests/rules/test_regulations.py` and
`tests/rules/test_regulation_service.py`, alongside the existing discipline, scene,
Off-Duty and M2 regressions. They cover exact consultation/concealment, independent
causes, actual future-period recovery and subsequent on-screen Punishment,
rollback/replay/concurrency, pause/revocation, controller/character changes and
native confirmation. Knowledge transfer to a replacement Handler, career archives,
all remaining discipline/playbook interactions and milestone acceptance remain
future work, rather than inferred successful consequences.
