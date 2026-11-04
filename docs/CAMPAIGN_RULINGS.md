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


Additional Frame Off-Duty interpretations adopted under delegated authority:

- `frame_reward_eligibility`: Capture Frame and Queen-holder eligibility at the actual Off-Duty roll; DoctorDoctor keeps the approved pre-Budget start ordering. Book PDF 27–28, 61, 65, 68, 71, 74, 78, 81, 84, 88; sheets PDF 18–26. The printed trigger does not order later replacement/Court transfers against outstanding choices. Binding actual earned eligibility preserves its owner without restoring old resources. Alternatives: Use the Frame and holder at the later submission time; Freeze all Frame bonuses at period start. Implementation: Existing immutable roll-state history is referenced and checked against the action, receipt, character and period. Only current Permissions are changed. Change impact: Future ordering changes require explicit pending-work review; do not move earned choices to a new holder or recalculate saved rewards.
- `frame_reward_observation`: The normal Frame Off-Duty triggers also apply when Void Observation replaces the ordinary roll. Book PDF 28 and Frame Permission triggers PDF 61–88. Observation replaces rolling Go Off-Duty while retaining Off-Duty recovery and the broader period; it does not expressly suspend Frame triggers. Alternatives: Suspend bonuses during Observation. Implementation: The common reward scheduler accepts an actual Off-Duty roll context. Full Observation integration remains pending. Change impact: A revised exclusion affects future Observation periods and outstanding reviews, retaining prior receipts.
- `queen_reward_dog`: The Queen holder cannot award itself while it is the Dog; it can choose another current Girl who is the Dog. Book PDF 88; sheets PDF 26. The parenthetical Dog restriction is attached to the self-award clause, rather than all recipients. Alternatives: Exclude every Dog recipient. Implementation: The actual Queen holder selects a legal current Girl; self-Dog is rejected server-side. Change impact: Review pending recipient selectors after a change; never revoke a completed award silently.
- `frame_prisoner_reward_repeat`: A particular character can earn a prisoner bonus only once from one actual custody/delivery record; joint contributors are not globally excluded. Book PDF 65 and 78; sheets PDF 19 and 23. An actual delivery should not be repeatedly re-presented as new, while the text supplies no exclusive single-captor quota. Alternatives: Permit repeat rewards for the same delivery; Allow one bonus total across all contributing characters. Implementation: Consumed delivery provenance is recorded per actual character ID. Current delivery-state checks are implemented; complete custody/event-history selection remains pending. Change impact: New pricing/eligibility policy requires explicit treatment of pending delivery claims and preserved consumed-source receipts.

All four remain printed-rule clarity-review items. A ruling is not a waiver for missing Observation, historical qualifying-delivery or Director-role implementations.


Observation nested choices (book PDF 28 / printed p.26), adopted under delegated authority:

- `observation_choice_overlap`: Player and Handler choose distinct consequences across the shared Observation list. Separate choose counts refer to one outcome list; distinct consequences avoid selecting the same surgery or assignment twice without source instructions for stacking. Alternatives: Permit the same consequence once for each human. Implementation: The reducer enforces distinct values within and across saved selections; each human still owns its exact count. Change impact: Changes affect legal pending selections and need explicit treatment of already selected/resolved effects; retain dice and completed effects.
- `observation_reprogram_owner`: The affected player chooses the retained current Identity and any approved fallback slot for Observation reprogramming, regardless of who selected that consequence. The text does not allocate the nested choice. Preserving the affected player's own Identity choice avoids treating non-Punishment reprogramming as the separately ruled inflictor-owned Punishment default. Alternatives: Let the human selecting reprogramming choose its Identity details; Always assign reprogramming details to the Handler. Implementation: A separate affected-player request applies the actual reset reducer and preserves protected/locked slots. Change impact: A new owner rule requires reassignment of pending requests; do not reset already settled Identities or impersonate an absent player.
- `observation_populace_controller`: The Handler plays the general populace for its actual public-display Tag and is recorded as that Tag's human giver. The source specifies the populace as giver but supplies no separate player role; the existing core Tag system identifies the human controller. Alternatives: Invite another explicit human to play the populace. Implementation: Public-display Tag detail is a separate Handler-owned request. Harpy Candidate uses its printed fixed label; neither is automatically marked. Change impact: Changing controller representation affects future Tag authority and pending choices, and requires an explicit migration for existing giver provenance.

These require printed-rule clarity review. NPC role invitations and appearance responses now have offline implementations. Director rule-mode, world triggers and remaining battle interactions are implementation gaps; these rulings do not waive them.


Director context interpretations (book PDF 192 / printed p.190), adopted under delegated authority:

- `director_overlap`: Overlapping Directors share one continuous Handler Girl-rules episode; additional arrivals do not restart Heat or grant another starting Identity set. The source defines a state while in the Director's presence, without stacking/reset rules for several Directors. One continuous context preserves its actual resources. Alternatives: Reset Heat and replace the Identities for every arriving Director; Create simultaneous independent Girl sheets. Implementation: The actual Handler selects two ordinary starting cards once; later overlapping presence binds its own source work to the existing context. The Handler stays outside the Pilot roster. Change impact: A change needs explicit treatment of active contexts and pending work; never reset spent Heat or duplicate existing cards silently.
- `director_exit_resources`: The final actual Director departure ends this rule authority without unmarking cards, granting Heat or restoring an older Heat balance. A later new presence starts its printed zero-Heat/two-Identity context. The source specifies the start but no exit recovery or resource restoration. Preserving actual resources prevents an inferred free recovery or banked reset. Alternatives: Restore the Handler's earlier Heat balance; Discard all Heat immediately on departure. Implementation: Departure is an actual separately owned human action. Context history and resource marks remain private canonical evidence; no timeout ends it. Shared Girl Play integration remains pending. Change impact: Revised exit behavior affects future episodes and active-context review, preserving prior receipts and actual resource changes.

Both require printed-rule clarity review. The printed zero-Heat/two-Identity start is separate from these interpretations. Actual presence is source-reviewed; merely introducing an NPC does not establish that the Handler is present.


- `director_controller`: use someone different from the current Handler to play
  the Director throughout this campaign. **Source distinction:** High Budget 1/1
  explicitly requires someone else (book PDF 151 / printed p.149). Generic NPC
  principles allow broad control (PDF 188–189); PDF 192's Director rules do not
  impose a universal separate-player restriction. The global restriction is a
  delegated campaign recommendation, keeping the opposed roles and their actual
  decisions distinct. The alternative is separation only for that Budget scene.
  Introductions, invitations and claims currently enforce the global policy. A
  Girl player may play the Director; actor identity must still distinguish those
  roles. A future relaxation requires scene-specific binding and preservation of
  the explicit Budget requirement, not silent reassignment of saved decisions.
  This remains a printed-rule clarity-review item.


`regulation_breach_review`: use the current informed Handler to record an actual
breach and choose current-context or next-Off-Duty discipline. Book PDF 17 / printed
p.15 permits concealed rules and further Punishment but leaves the reporting
procedure unspecified; PDF 18 requires Handler consultation for Moderate effects.
This is a delegated recommendation requiring printed-rule clarity review. Alternatives
are adjudication by the original inflictor, or affected-player confirmation. The
implementation uses explicit human accounts and actual source events, with no
passive chat judgment. Each breach retains its own cause; future-period deferral
cannot be pulled into the current period. Changing this policy needs knowledge and
pending-cause migration, without replaying discipline or exposing a concealed rule.


`repair_shortage_timing`: a Low Budget 4/2 event rolled during Off-Duty binds to
the next actual dispatched mission, its end and the following recovery period.
Source: book PDF 150 / printed p.148; delegated recommendation, clarity review
required. The source says next/current mission; this lifecycle starts Off-Duty
only after all actual missions finish, so no active current mission exists at the
new event. Alternative: treat the preceding mission as current and restrict this
period immediately. Preserve each source and actual dispatch/end/period provenance;
overlap retains the one-Asset limit without extra free quotas. Revision requires
explicit treatment of armed scopes and pending quotes, preserving prior recoveries
and payments without retroactive damage or charges.


`supply_observation`: apply an assigned current-period missed-supply −2 to both
ordinary Go Off-Duty and its Void Observation replacement. Book PDF 150 / printed
p.148 names this Off-Duty roll; PDF 28 / printed p.26 replaces it. This delegated
recommendation requires clarity review. Alternative: ordinary rolls only. The
same period consequence should survive replacement, with one source-proven OS
random recipient, actual character binding and separate pre-roll modifier. Changing
the policy requires review of unrolled reservations and assigned losses, preserving
known dice, receipts and recipients without redrawing or moving it to a new body.


`scientific_observation_selection`: the current Handler represents the Foundation's
scientific demand and selects one or two actual Girls, explicitly answering each
hiding review. Sources: book PDF 150 / printed p.148 and PDF 28 / printed p.26.
This delegated recommendation requires clarity review. Alternatives: Cadre
volunteers or a random draw. Validate real character/period targets; an order does
not grant transport, treatment, NPC acceptance or a Girl's voluntary response.
Changing selection ownership requires actual owned requests and pending-order
migration, preserving receipts, original characters and prior human answers.

`scientific_observation_overlap`: keep one actual same-period Observation roll with
distinct causes when a scientific demand overlaps an existing order. Same sources;
delegated clarity-review recommendation. Alternatives: extra independent rolls, or
exclude already observed Girls. Observation replaces the period recovery; the book
does not prescribe another cycle for an overlapping cause. Keep original provenance
and a real additional scientific cause, with a fresh explicit pre-reservation hiding
review. Any revision must preserve known rolls, Status loss, answers and owed
consequences, without silently discarding or doubling them.


`director_adjudicator`: A currently controlled, explicitly cast Director supplies Handler-rule replies to the actual Handler acting under Girl rules. OOC scene facilitation remains separate. Source: Book PDF 192 / printed p.190. Delegated recommendation; printed-rule clarity review required. The Director uses Handler rules while the physical Handler uses Girl rules. Keeping the two roles distinct prevents self-adjudication or granting the Director player global GM knowledge. Alternative: Keep every Handler-rule reply assigned to the original OOC facilitator. Director offers its actual cast role. The acting Handler confirms that Director when reserving a Play. Persist both actual actor references and controllers, and revalidate current presence and control on every response. Changing this ruling: Changed adjudication needs explicit recovery of outstanding decisions with preserved receipts and prior owned answers; no silent controller transfer.


`actor_tag_disputes`: When mixed-role Tag proposals compete, the adjudicator proposes one actual proposal and all scene humans explicitly agree before its modifier applies. A rejection returns to discussion. Source: Book PDF 11 / printed p.9. Delegated recommendation; printed-rule clarity review required. The source permits discussion as an alternative to Status or rock-paper-scissors. Unanimous recorded discussion handles roles outside Pilot Status without inventing NPC, Harpy or Director ranks. Alternative: Use the printed expanded Status hierarchy with explicit current fictional exceptions. One response per real human, not per controlled character. Only other humans may propose a Girl Tag, through one actual cast role. Preserve the original proposals and never infer agreement from timeout or silence. Changing this ruling: A revised dispute procedure needs explicit pending-proposal migration and source-correct actual actor ranks. Preserve applied modifiers and already recorded human decisions.


`comforts_qualification`: Creature Comforts waits for an actual future ordinary Go Off-Duty roll of 8 or more after post-roll modifiers. Void Observation does not consume that opportunity. Source: Book PDF 16 / printed p.14; PDF 28 / printed p.26; owner delegated authority. Delegated recommendation; clarity review required. The source expressly names rolling 8+ to Go Off-Duty. Observation has its own replacement Play and result table, so retaining the paid benefit until the named roll preserves that trigger. Alternative: Treat an 8+ Void Observation replacement as qualifying too. Use actual raw-roll state to prove the purchase existed before dice, the actual final receipt/action and original character. Low rolls and Observation leave the paid purchase waiting; a queued opportunity requires the owners actual scene or explicit decline. Change impact: Changing this interpretation needs review of waiting purchases and unfinished opportunities. Preserve known qualifying receipts, actual scenes, paid costs, granted Assets and human decisions.


`comforts_stacking`: Each separately paid Creature Comforts purchase has one optional opportunity on its next actual qualifying ordinary Go Off-Duty roll. Multiple paid purchases may qualify on the same roll. Source: Book PDF 16 / printed p.14; PDF 28 / printed p.26; owner delegated authority. Delegated recommendation; clarity review required. Each receipt pays for its own future benefit. The text gives no limit of one outstanding purchase or one benefit irrespective of how many Permissions were paid. Asset limits still apply to every actual grant. Alternative: Limit the player to one pending purchase or one opportunity per recovery period. Bind each immutable paid source once to one real roll and one owned improvement scene. Never multiply an unpaid source; each granted Asset records its purchase and remains subject to the Girl Asset cap and non-Void replacement rule. Change impact: A new stacking limit must address already paid waiting purchases explicitly, without deleting costs, fabricating refunds or reusing known rolls for extra grants.


`comforts_decline`: Declining the optional Creature Comforts scene at its actual next qualifying roll consumes that paid opportunity without refund; it grants no Asset or scene. Book PDF 16 / printed p.14; owner delegated authority. Delegated recommendation; clarity review required. The purchase pays for an opportunity at the next named qualifying roll, and the scene is optional. The source provides no refund or repeated opportunity after an explicit decline. Silence still leaves the decision pending. Alternatives: Keep an unused paid benefit waiting for a later qualifying roll; Refund a declined optional scene. Disclose the cost and no-refund consequence before the owner confirms decline. Preserve the original cost, qualification and explicit owned decision. Never infer decline from absent humans or a timer. Change impact: A different campaign interpretation needs explicit treatment of declined opportunities, preserving their real costs and decisions. Do not fabricate refunds or retroactively grant Assets.


`gorgon_destroyed_core_guard`: A destroyed original designated Gorgon guard satisfies the Asset condition for Core exposure. The actual recorded conversational weakness must still be fulfilled and explicitly confirmed. Source: Book PDF 162, 164 / printed pp.160, 162; delegated owner authority. Delegated recommendation; printed-rule clarity review required. Destruction removes the actual guarding Asset rather than restoring protection or leaving an impossible requirement to damage an Asset that no longer exists. Preserve the independent weakness condition and actual Core destruction for death. Alternatives: Require a new explicit Core-plan review after every designated guard destruction.; Treat destruction as insufficient until the table resolves a different means of fulfilling the Asset condition.. Implementation: Keep destroyed actual Assets as immutable canonical history outside usable Assets. Original Core/protection references retain provenance; destruction never automatically exposes or kills the Gorgon. Change impact: Review existing pending Core exposures and actual destruction sources before changing this interpretation. Preserve historical Asset destruction and confirmed Core outcomes; do not resurrect an Asset or reroll a known result.


`benevolent_defense`: Benevolent Gorgons cannot initiate Attack or Collateral Damage, but can defend when another Gorgon pits Assets against them. The Handler chooses the actual contest winner. Source: Book PDF 162, 167 / printed pp.160, 165; delegated owner authority. Delegated recommendation; printed-rule clarity review required. The Attack rule explicitly includes a Gorgon target and a Handler-chosen Asset contest. The Benevolent restriction forbids initiating its attack, without requiring it to lose an opponent-initiated contest; a defensive result can follow from the attacker striking its protection. Alternatives: Require Benevolent Gorgons always to lose or avoid any Asset contest.; Permit defense but require a separate bespoke defensive outcome rather than the printed contest.. Implementation: Reject Benevolent initiators in both NPC and Gorgon Attack commands. Permit it only as the actual defender of another Gorgon, with the actual Handler winner and chosen losing pitted Asset. Change impact: Review pending defensive contests when changing this ruling. Preserve prior actual winner decisions and destroyed-Asset history rather than silently undoing consequences.


`refusal_bonus_overlap`: every waiting Low Rebellion 1/2 occurrence supplies its own
+2 to the next actual Girl Disobey Orders roll; that one roll consumes all waiting
occurrences. Source: book PDF 147 / printed p.145; delegated owner recommendation,
printed-rule clarity review required. Each occurrence names the next refusal;
there is no printed non-stacking limit or permission to postpone one source.
Alternatives: use only one queued bonus per refusal, or collapse overlaps to a
single +2. Keep distinct actual source works/events and consumption in the same
transaction as the roll, separately from Heat and post-roll Tags. A later policy
change must review unrolled reservations and waiting sources, preserving known
dice, receipts and consumed sources without refunds, reuse or silent postponement.
