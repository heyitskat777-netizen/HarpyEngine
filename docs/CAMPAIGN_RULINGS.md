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
| `strain_repeat_timing` | A repeat is the same chosen track/severity/row/column. It flags a severity change at the next period start; retain the current receipt and chosen event | Book PDF 142, 144–145, 147–148 and 150–151 say severity changes at the start and list repeats, without specifying reroll timing |
| `strain_cascade_count` | Count earlier selected occurrences on that same track across the campaign, including Low/High, repeats and recursive events, excluding the current event. At two or fewer, queue one Low and one High roll; otherwise queue an unused Endgame choice | Book PDF 145, 148 and 151 say “other” events without defining the counting window; persistent occurrences preserve a reproducible threshold |
| `doctor_start_order` | DoctorDoctor owners record credit/no-trigger before Budget start review. Apply High Budget Obsolescence once using the resulting start severity | Book PDF 71 has simultaneous Off-Duty triggers; this preserves the earned credit record before a possible compulsory scrap changes the Frame |

The DoctorDoctor recipient and Sedation duration recommendations were explicitly accepted by the owner's instruction
to use all recommendations going forward. Runtime integration is tracked by the
M3 evidence report; being in this table alone does not mean it is implemented.
The replacement interpretation uses that delegated authority and remains flagged
for clarification. Its alternative is to let replacement create an unlocked slot.
Changing it affects future replacement/rename events and UI selections; existing
receipts and lock provenance must not be rewritten silently.
The three Strain/Doctor ordering decisions also use delegated authority and remain
flagged for clarity review. Alternatives include changing severity immediately
after a repeat, counting only distinct events or only the current cycle, and
capturing a deferred pre-scrap credit snapshot. Revising these changes future
queue ordering, thresholds and pending-work interpretation; it must not reroll
saved dice or discard a recursive request. All table labels are selection aids,
not claims that the selected effects are implemented. Exhaustion of all enabled
unused Endgames remains a source gap; the system does not recycle slots or reroll.

Additional world interpretations adopted under delegated authority:

- `world_grid_steps`: a one-square move may use any of the eight neighboring
  squares, and a Directed step must reduce grid distance toward its goal. The
  Handler chooses among legal steps; arriving at an existing goal does not invent
  a new destination. Book PDF 121–123 describes squares and eight neighboring
  territory squares without defining diagonal travel. Orthogonal-only movement is
  the alternative. Changing this affects future movement, not historical positions.
- `gorgon_class_change`: “change type” for an Aggressive Gorgon outside a location
  means an explicit behavior-Class change, retaining its body, existing Asset
  damage/count, archetype Types, Core and reveal status. Book PDF 123 calls this
  a type despite Aggressive being a Class on PDF 165. Literal archetype-Type
  replacement is an alternative. New-Class Asset counts apply to creation, not
  free retroactive resets; revised policy needs explicit pending-move review.
- `gorgon_reappearance`: the returning Gorgon keeps existing Assets/damage and
  gains exactly two intact Assets plus a distinct additional archetype Type. Its
  rebuilt Core begins unexposed with an explicitly specified current Core plan.
  Already multi-Type bodies retain their Types; Sprite followers inherit current
  leader Types. Book PDF 145 omits old repair/Core timing and repeated multi-Type
  cases. Fully refreshing the old body or replacing a secondary Type are
  alternatives. Changes affect future revivals, preserving prior death receipts.

These remain clarity-review items. Private world persistence of the initial Class
0 is hidden from the player map, preserving the secrecy instruction on PDF 122.
Actual Type headings include Growth and Parasite on PDF 175–176, even though the
outline on PDF 168 lists only six. All eight are represented; this is a source
inventory correction rather than a new campaign archetype.

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


Additional observation/reset interpretations adopted under delegated authority:

- `reprogramming_reset_marks`: restore ordinary starting slots as fresh, unmarked
  Identities, copying the selected current label into the printed Malfunctioning
  slot (or the approved player-selected fallback). Preserve the actual protected
  extras and Paired Identity, including their marks. Active Sedation follows its
  stable replacement slot; an explicit printed removal still removes the Identity
  and its restriction. The book's reset wording does not state mark/ID handling.
  Alternatives are retaining the selected card's old mark, or resetting even
  protected/locked resources. This recommendation uses the existing starting
  baseline and the accepted protection/lock decisions. Slot metadata adds no card,
  Heat or recovery. Changes apply to future resets and require explicit review of
  pending work; old receipts are retained.
- `identity_duplicate_labels`: allow matching labels on separate stable cards in
  M3, using their IDs and slots for choices and marks. Reprogramming can retain a
  default label that is restored elsewhere, and the book does not forbid that.
  Rejecting it or merging the cards would change legal choices/resource counts.
  The four ordinary/Paired slot cap and protected extras still apply. Trusted M3
  policy controls this; a client cannot enable it. Existing M2-only policy retains
  its prior behavior. A future uniqueness change must explicitly address existing
  distinct cards, marks and pending choices. Both decisions require printed-rule
  clarity review; neither makes the full Observation flow implemented or reviewed.
