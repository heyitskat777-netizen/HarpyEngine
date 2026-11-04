# Campaign rulings and clarity register

The owner authorizes Codex to use its recommendations for future unclear rules,
record them here and continue development without asking about each interpretation.
Earlier explicit owner decisions take precedence. Printed rules remain the source
authority; these interpretations are campaign policy, not claims about the book.
They do not replace actual player choices, consent, independent review or release
approval. Ancillary playbooks remain deferred and disabled by default.

`rules/registry.json` stores stable ruling IDs, source, decision, authority,
rationale, alternatives, policy key and revision. Existing rulings are explicitly
owner-approved. New recommendations adopted under the delegation use
`authority: delegated_recommendation`. `clarity_review: true` flags each item for
later comparison with an official clarification. Inventory/review status is
separate: a ruling never makes an unimplemented rule executable or verified.

## Current decisions

| Ruling / policy | Decision | Source or reason clarification was needed |
|---|---|---|
| JANUS-B label | Official JANUS rules with JANUS-B as the server label | Owner explicitly chose a cosmetic alias, not custom mechanics |
| Starting resources | Heat 0, CONSUME Quiet, DoctorDoctor zero marked boxes; unmarked Identities/maxims, undamaged Assets/body parts, Personal NPC Bonds, zero Permissions, no acquired Requisitions/extra Tags; retain printed exceptions | Owner-approved campaign defaults for unspecified initial state |
| Intense Bond Tag modifier | ±2 at both Personal and Intense | Book PDF 13 / printed 11 explicitly lists ±2 under Personal without repeating it under Intense |
| `reprogramming_fallback` | Owner chooses an ordinary starting slot if Malfunctioning is absent; preserve protected extras | Book PDF 28 / printed 26; five base Girl sets omit Malfunctioning |
| `standard_unpriced_cost` | Creature Comforts, Privacy and Asset Installment cost 1 Permission each | Book PDF 16 / printed 14 and sheets PDF 40 omit prices |
| `extra_repairs` | Current Handler explicitly quotes each paid extra Asset repair | Book PDF 150 / printed 148 omits the price; ordinary free recovery is separate |
| `ace_bonus` | Current Ace receives +1 even when absent | Book PDF 16 / printed 14 does not tie the separate bonus to participation |
| `punishment_details` | Inflictor chooses unspecified details; explicit printed ownership overrides it | Book PDF 17–18 / printed 15–16 does not assign every selection |
| `failure_dog_overlap` | One actual Punishment satisfies both causes in the same mission; retain both records | Book PDF 16–17 / printed 14–15 lists both requirements without saying whether they stack |
| `sedation_small_set` | Mark all remaining Identities if fewer than two; set Heat to zero, retaining explicit Paired exceptions | Book PDF 17 / printed 15 omits a fallback |
| `princess_ace_check` | Check Ace after promotion; Princess and normal mission/Ace rewards remain separate | Book PDF 32 / printed 30 is ambiguous about the conditional timing |
| `compulsory_frame_package` | Handler defines the exact package for each compulsory replacement | Book PDF 29 / printed 27 and PDF 71 / printed 69 omit replacement resources |
| `replacement_frame_repeat` | Require a different official Frame playbook; aliases do not count as different | Same replacement passages do not clearly address repeating a playbook |
| `compulsory_frame_charge` | Free; optional paid Frame Swap remains separate | Book PDF 16, 29 and 71 omit a compulsory-replacement price |
| `doctor_credit_recipients` | Current canonical Pilots only; another Pilot can receive it even when its player is offline | Book PDF 16 defines Pilot rewards, while PDF 71 says someone else; this uses the core reward scope |
| `sedation_duration` | Locks last through that specific Off-Duty period, including pauses/restarts; clear at its explicit end | Book PDF 17 omits duration; a bounded period fits Minor discipline without inventing permanent treatment costs |
| `sedation_identity_replacement` | A Tag replacing a Sedated Identity keeps its mark and period lock; renaming the protected Paired slot also retains it. An explicit printed removal still removes that Identity | Book PDF 17 says these Identities cannot be unmarked during Off-Duty, without addressing replacement; retaining the slot restriction prevents a cosmetic replacement from becoming an extra recovery |

The DoctorDoctor recipient and Sedation duration recommendations were explicitly accepted by the owner's instruction
to use all recommendations going forward. Runtime integration is tracked by the
M3 evidence report; being in this table alone does not mean it is implemented.
The replacement interpretation uses that delegated authority and remains flagged
for clarification. Its alternative is to let replacement create an unlocked slot.
Changing it affects future replacement/rename events and UI selections; existing
receipts and lock provenance must not be rewritten silently.

## Changing a ruling

1. Identify its stable registry ID/policy key and official source. Record the new
   decision, reason, authority and a higher revision; retain the old decision in Git
   and existing immutable receipts. Preserve the distinction from printed rules.
2. Supported values live in trusted `owner_m3_rulings` policy (M2 defaults have their
   existing separate policy fields). Some fields intentionally accept only the
   implemented value. A different value needs its reducer/service/UI changes and
   tests before configuration accepts it. There is no in-game ruling editor yet.
3. Update fixtures, documentation and exact source-interaction tests. Pending forms
   and approvals tied to old state/policy/registry require fresh review. Do not
   silently recalculate old rolls, rewards or completed scenes.
4. For an existing campaign, decide explicitly which pending/future events adopt
   the new revision and migrate stored state if required. Back up live data and
   preserve immutable provenance. Development never edits live policy implicitly.

Future entries must include the ambiguous source, recommendation and rationale,
reasonable alternatives, authority, implementation status and change impact.
Log unknown/missing implementations separately rather than inventing outcomes.
