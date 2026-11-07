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


`beneath_private_choices`: for Put Someone Beneath You, the printed chooser selects
the effect; the affected Girl supplies the actual private Bond endpoint or
counter-damaged Asset. Explicit Tag selection remains with its printed chooser.
Punishment details retain the owner-approved inflictor-owned rule. Source: book
PDF 22 / printed p.20; delegated recommendation, printed-rule clarity review required.
The text specifies effects but omits ownership of those private subchoices. This
keeps the selected mechanical effect while preserving private inventories and NPC
relationships. Alternatives: expose/select every resource to the effect chooser,
or negotiate each resource at the table. Trusted policy must explicitly set
`beneath_private_choices: affected_owner` before this new Play is enabled. A change
requires reviewing unfinished detail requests, preserving known rolls, original
characters, selected effects and completed outcomes; never infer a player's reply.

## Temporary Requisition removal and restoration

`temporary-requisition-restoration` / policy `privilege_restoration`: delegated recommendation, printed-rule clarity review required. Book PDF 16–17 / printed pp.14–15 calls Revoked Privileges temporary but gives no duration or restoration owner. The inflictor states the restoration condition and explicitly confirms when it is met; the original affected owner then restores the actual resource and chooses any required legal Asset replacement. Neither response is inferred from chat.

Alternatives are automatic expiry at the next Off-Duty period, or Handler ownership of every restoration. The selected interpretation preserves the actual inflictor's decision and makes the temporary removal reversible without inventing elapsed time. Future adjustment must preserve existing paid receipts and original resources and explicitly review outstanding conditions.

For implemented purchases, an Asset Installment retains its original Asset ID, damage, Void state and Frame while unavailable. Pending Creature Comforts cannot qualify or grant during suspension; already consumed benefits are ineligible. No refund, repair, duplicate reward, transfer to a replacement character or replacement Frame is granted. Other Requisition types need their own implemented suspension effects before this route can handle them.

## Parallel creation, lifecycle and paid-scene rulings

These delegated recommendations remain flagged for printed-rule clarity review. Evidence and certification are tracked separately.

### `handler-starting-creation-ownership` (revision 1)

Handler creation uses original-appointment/persona-bound owned shared starting proposals. The affected original Girls accept or decline shared history, Bond, rank and printed Trainer starting phrases. Private Handler details remain private. Late initial activation preserves any already stronger M2 Bond and moves selected Ace/Dog while preserving other relative order.

Source: Book PDF124,126,128,131,134–135,137,139,141 / printed pp.122,124,126,129,132–133,135,137,139; delegated owner recommendations

Reason: The book assigns starting selections but does not specify digital agreement ownership, late initialization over accepted M2 resources, or custom versus printed Bond-story selection. Shared exact owned proposals protect human history choices without revealing Handler background/playbook/gear. Already stronger canonical relationships must not silently downgrade during initial M3 persona creation.

Alternatives: Apply starting Bonds/ranks directly without shared-history agreements.; Set every starting Bond to the exact printed depth, downgrading accepted stronger M2 relationships.; Require printed histories exclusively, without custom human-authored histories.

Implementation: Use trusted handler_creation=owned_shared_choices_preserve_existing. Starting stories may be human-authored or selected prompts; only selected Trainer printed stories automatically install their named phrase sets. Insurgent selects1–2 actual living Handler NPC Bonds Surveilled and1 actual living NPC Bond Sympathizer; overlap is allowed because the source does not say the labels are exclusive. Gear descriptions create no extra NPCs, vehicles, map movement or surveillance. Canonical persona identity is distinct from account and appointment event; old forms cannot reactivate or overwrite it.

Changing it: Change future creation proposals prospectively. Existing accepted source-bound proposals, canonical initial effects, current relationships and private draft history require explicit review before reinterpretation; do not reset M2 resources or fabricate another human response.

### `defeat-medical-waking-and-unused-playbook` (revision 1)

Actual medical waking clears only confirmed incapacity/vitals; the original Girl then owns an available Girl Play exchange from a currently unused base Girl book.

Source: Book PDF29 / printed p.27; delegated recommendations

Reason: The injury option names waking and an unused playbook but gives no digital medical confirmation or definition of unused. Actual current native playbooks define use without treating a borrowed single rule as an extra character class. Care evidence and waking remain explicit human facts.

Alternatives: Treat borrowed rules as occupying their entire source playbook.; Immediately wake the Girl or repair all resources automatically.

Implementation: Original patient proposes actual help; current appointed Handler confirms that exact source context. Recovery preserves placement, vessel, custody and damaged Assets. Explicit restored vital signs are separate from waking. Original CID owns the subsequent swap. Only fully implemented acquisitions are selectable; other actual rule IDs remain runtime_pending, with no synthetic acknowledgment resolver.

Changing it: Changing unused-book semantics affects future offers; existing acquired ownership remains source-bound. Changing care authority requires review of pending exact proposals; do not retroactively fabricate medical help or consent.

### `girl-playbook-baseline-epochs` (revision 1)

Changing the whole Girl playbook establishes a new native baseline and preserves still-owned explicit third-party acquisitions and sourced setup; prior swap masks are archived with their old epoch.

Source: Book PDF29 / printed p.27; delegated recommendation

Reason: The low Defeat result changes the Girl book but does not direct loss of separately acquired Plays. Old masks apply to the old baseline and must not suppress a newly provided native rule. Boolean rule ownership avoids granting duplicate effects when a prior acquisition is now native.

Alternatives: Discard all previously acquired rules on any Girl playbook change.; Keep old removal masks active against the new native baseline.

Implementation: change_playbook_runtime returns a new sheet and source fact containing prior runtime. retained_rules plus current swaps determine ownership; native and acquired instances never stack the same rule. Existing protected identities and distinct body/frame resources remain caller-owned responsibilities. Required new-book stateful setup stays real required work.

Changing it: Any different retention rule needs explicit review of existing acquisitions and affected pending setup. Preserve previous epoch facts rather than rewriting swap history.

### `acquired-higher-standard-owned-setup` (revision 1)

Acquired To a Higher Standard uses the same three original human choosers as native ownership: self, one actual bonded other Girl, and the currently appointed Handler.

Source: Book PDF32 / printed p.30; Defeat PDF29 / printed p.27; delegated recommendation

Reason: A never-Princess borrower lacks native draft setup. Applying the printed chooser instructions to the actual acquiring Girl preserves original human authority without changing class, copying stale draft choices or leaving a nominal nonfunctional capability.

Alternatives: Give the borrower default standards chosen by the bot.; Reject this otherwise implemented acquisition forever when native draft labels differ.; Apply the rule before the original other choosers respond.

Implementation: Source-bound private standards work stores each actual original choice/event independently. Missing chooser stays pending; owner may withdraw/restart with current real participants. Medical acquisition compiles all three choices and atomically activates them with the actual rule exchange. A new native baseline can invoke the same setup independently. Handler standard counts as an order. Mission-end trigger and review follow current rule ownership, so removed native rules stop and borrowed rules work. Preserve explicit after-promotion Ace Permission plus normal Ace bonus.

Changing it: Chooser/consent changes invalidate only affected pending exact proposals; do not transfer another human response across CIDs or Handler appointments. Existing native accepted M2 standards remain reusable; runtime ownership is distinct from private draft class labels.

### `girl-book-change-continuous-setup` (revision 1)

A full Girl book change retains the original body and actual resources and configures only newly active continuous-rule requirements; it does not rerun character creation.

Source: Book PDF29/printed27; PDF31–58/printed29–56; delegated recommendation

Reason: Defeat says change the Girl playbook, without resetting Identities, purchasing new Assets, advancing rank or introducing new NPCs. Continuous rules still need actual owned choices, and their source authority must follow original people rather than account labels.

Alternatives: Recreate the entire Girl and supply two free starting Assets, new Bonds and initial Ace rank.; Change only the class label and leave stateful native rules unusable.

Implementation: Create original-CID/new-baseline required work immediately after the actual Defeat event. Newgirl requires current Handler assignment and actual Mentor callsign; Bonded requires nominated original Pair acceptance and owner selection of the existing Paired slot or one ordinary slot renamed Hers. Preserve protected extras and existing Paired protection; install Personal/Intense depth without Heat rewards or weakening a stronger Bond. Oldgen chooses two maxims. Princess uses actual three-chooser standards without a new-game Ace reset. Vatgrown names its actual DNA basis, chooses desires for retained actual starting NPC investors, and the current Handler chooses their own desires. Casualty initializes nine typed parts only if no prior parts exist, preserving prior damage. AM and Mockingbird retain actual bodies, Identities, limiter/protected evidence and Assets; no extra body, limiter reset or automatic Void corruption. Native unimplemented Plays remain fail-closed independently.

Changing it: Change prospective setup requirements only after reviewing current pending choices and original CID/epoch. Do not invent human responses, heal old damage, downgrade Bonds or overwrite another person’s protected Identity. Source review is still required for the printed omission.

### `initial-handler-persona-adoption` (revision 1)

First creation describes the existing Handler; actual existing relationship graph edges adopt that first persona. Later persona replacements preserve old source identities and gain no inherited authority.

Source: Book PDF124/printed122; delegated digital identity clarification

Reason: M2 already has actual Handler relationships before a named M3 persona exists. Treating first persona creation as a new person would silently orphan valid Bonds; treating every later persona as the same person would transfer authority across replacements.

Alternatives: Discard all pre-persona Bonds on first persona creation.; Transfer every prior persona relationship to each future replacement automatically.

Implementation: First activation migrates actual legacy Handler(None) edges, installs the actual first persona, rebinds those edges to its actual persona ID and sets printed starting depths through the single actor graph. Already stronger Bonds are preserved. Only legacy Tags lacking both giver_actor and giver_character receive an explicit first-persona binding; already bound setter evidence remains unchanged. Replacement personas migrate old graph before replacement and never rebind it to the new person.

Changing it: Any alternative identity model requires explicit graph/Tag-source review before applying to a populated campaign; preserve old original-person evidence and do not mint replacement consent.

### `privacy-next-active-period` (revision 1)

Privacy binds the first actual Off-Duty activation after payment; an already-active-period purchase waits for the next activation. Either ordinary or Void Observation is permitted.

Source: Book PDF16 and27–28 / printed14 and25–26; delegated recommendation

Reason: Privacy says next off-duty without a roll8+ condition; Observation is an alternate off-duty route. Freeze actual activation-state paid sources and original characters.

Alternatives: Bind only ordinary Go Off-Duty.; Permit an already-active interval retroactively.

Implementation: Actual period activation state must contain the paid original receipt; no late purchase claims a known activation. Companion original CID remains bound.

Changing it: Review outstanding period-bound benefits before adjusting timing; preserve paid receipts and consumed outcomes.

### `paid-scene-owned-decline` (revision 1)

The original buyer may decline an unused qualified optional scene without refund; no timer or Handler acknowledgment chooses for them.

Source: Book PDF16 / printed14; existing Comforts decline recommendation applied to scene benefits

Reason: Printed benefits are optional paid opportunities, not refundable currency exchanges or mandatory invented scenes.

Alternatives: Refund unused benefits.; Carry qualified opportunities to another period.

Implementation: Record actual owned decline; qualified requests remain pending until their actual owned scene or decline.

Changing it: Preserve prior payment and decisions; explicitly review unfinished qualified requests.

### `privacy-owned-ending` (revision 1)

Either original participant may explicitly end Privacy pause-safe. Actual original career endings terminate protection without fabricated consent, while old scene audience remains private.

Source: Book PDF16 / printed14; delegated recommendation

Reason: No interruptions protects the two Girls against outsiders; it does not force continued human participation or let delayed delivery publish old scene details.

Alternatives: Require both participants to approve ending.; Let Handler or timers end protection.

Implementation: Owned end records no automatic travel. A career end records actual archive/ended ActorRef rather than pretending voluntary close consent. Closed scene IDs require fresh public scene identity; proven existing continuations may resolve privately.

Changing it: Preserve original audience and known rolls; never retroactively expose earlier scene text.

### `visiting-home-supervision` (revision 1)

Visiting Home uses an actual Foundation-affiliated supervising role, whose human owns agreement before actual co-travel. Ordinary Go Off-Duty8+ qualifies; Observation does not.

Source: Book PDF16 / printed14; delegated recommendation for supervision detail

Reason: The benefit is Foundation-supervised; source does not name a required supervisor playbook or add approval/payment. Use actual Controller/ActorRef and actual Foundation affiliation, not invented NPCs.

Alternatives: Require current Handler personally.; Let arbitrary unknown actors supervise.

Implementation: Actual current Foundation Pilot/Handler or canonical Foundation-employed/affiliated NPC/external Pilot can supervise. The body and supervisor co-travel offstage and return via source-proved physical journey, preserving original positions and injuries.

Changing it: Review unfinished supervision agreements if eligibility changes; never transfer old consent to a new controller/body.

### `privacy-death-trouble` (revision 1)

After actual death/execution in active Privacy, current Handler chooses actual inquiry or supported Punishment. The original survivor owns response/refusal; with none, Handler records concrete method/question/report and known/unknown evidence.

Source: Book PDF16 / printed14; delegated recommendation

Reason: The book promises trouble without specifying a mandatory Punishment. Require actual human-authored consequence and preserve secret prior-room content rather than inventing guilt or disclosure.

Alternatives: Always inflict Punishment.; Allow a generic handled checkbox.

Implementation: Actual investigation creates typed question/method and surviving original human reply/refusal, explicitly shared with Handler. No survivor uses actual Handler-authored investigation report, with no manufactured NPC or witness. Punishment routes to real discipline work and effects.

Changing it: Preserve actual recorded questions/responses, private room audience and original character binding; review unfinished source-linked consequence explicitly.

### `career-incarnations-and-original-resources` (revision 1)

A new character on the same Discord account has a fresh gameplay incarnation; the predecessor's immutable sheet, resources and relationships remain original-character history.

Source: rulebook PDF 18 / printed 16; PDF 29 / printed 27

Reason: Printed compulsory new-character outcomes require an actual new Girl. Reusing an account or stable SQL profile must not transfer the previous Girl's authority or rewards.

Alternatives: Delete the original sheet and receipts; Reuse the account's old canonical identity and resources

Implementation: Canonical IncarnationBinding separates gameplay CID from stable SQL profile and receipt FK. Fresh creation starts empty progress and requires explicit Handler starting Status. Actual archived participation remains source readable.

Changing it: Different lifecycle identity policy would require an explicit audited data migration; ordinary accounts never acquire old authority automatically.

### `single-survivor-ace-and-dog` (revision 1)

A one-Girl roster is both actual Ace and actual Dog; Ace takes precedence for the single numeric Status modifier. Empty rosters have neither role.

Source: rulebook Status and mission-position benefits/consequences; PDF 14 / printed 12

Reason: Preserves the actual highest and lowest positions after genuine career endings without inventing another Pilot or blocking survivors forever.

Alternatives: Block all mission completion until a second Girl is activated; Apply only one of the two printed position consequences

Implementation: Current Ace receives genuine Ace benefit; the one survivor also receives Dog consequence. Departed original participation never rewards or punishes a replacement by UID.

Changing it: Changes affect future one-Girl mission benefits and Status rolls; original mission records remain immutable.

### `original-return-with-one-active-girl` (revision 1)

An imprisoned Girl may resume after an actual Handler offer and her original human owner's choice. If another Girl is active, preserve her in an immutable reserve archive rather than overwriting her.

Source: rulebook PDF 18 / printed 16 explicitly allows Handler-authorized return; active-account coordination is a campaign implementation ruling

Reason: Allows the printed return while avoiding two canonical Girls sharing UID-only controls, disappearing replacement resources, or forged owner choice.

Alternatives: Never permit the printed return; Silently overwrite the replacement; Allow simultaneous same-account Girl control before all workflows support multiple originals

Implementation: Explicit return Status is bound to the exact other-original roster. Keep saved resources without healing, invented location or new piloting consent. Resolve the current Girl's actual obligations, Helplessness, custody, journey, mission, Off-Duty and protected-scene commitments before switching. Only imprisonment and explicitly reserved originals are eligible; death, Execution, Retirement and Harpy conversion do not resurrect.

Changing it: A future multi-character account UI could replace reserve switching, but must preserve source CIDs and old obligations.

### `historical-bonds-remain-original-bound` (revision 1)

Career ending alone does not erase all historical Bonds. Preserve exact original ActorRef edges; their controller's replacement receives none of them.

Source: rulebook PDF 13 / printed 11 and explicit Bond-removal effect PDF 196 / printed 194

Reason: The source explicitly specifies all-Bond erasure for Lobotomy; inventing universal erasure on death or imprisonment would add an unsupported effect. Conversely account IDs are not fictional people.

Alternatives: Erase every Bond on every career ending; Transfer Bonds to a replacement controlled by the same human

Implementation: Typed graph migrates each legacy numeric/NPC edge to one source-bound authority; zero-depth tombstones prevent fallback. Above-Intense Heat goes only to actual live resource owners, including the distinct Harpy port, never another controlled actor. Source conversion may explicitly rebind the same fictional person to her Harpy body.

Changing it: Future erasure or weakening applies through actual original endpoints and preserves prior audit; historical actors do not acquire replacement Heat.

### `lobotomy-reset-protection-and-cap` (revision 1)

Lobotomy resets ordinary starting Identity slots, erases the inflictor's two eligible slots, preserves explicitly protected Identities, and uses the normal ordinary four-slot cap for an implanted Identity.

Source: rulebook PDF 196 / printed 194 together with the actual protected-Identity and ordinary-cap rules

Reason: A broad reset should not silently override a printed protection; implantation does not state a cap exception. Stable slots preserve Sedation marking rather than granting an unrelated unmark.

Alternatives: Erase protected extras and protected Paired slots; Treat the implant as an unlimited fifth ordinary Identity

Implementation: Inflictor chooses unspecified details under the explicit owner ruling. The reset-then-erase option has exactly two eligible ordinary slots removed; new memory has a described Identity, with an eligible replacement only when still at cap. Existing protected extras and surviving locked slots retain their actual protections/marks.

Changing it: Changing this interaction affects future surgeries; already applied surgeries remain source records and require explicit correction rather than recalculation.

### `lobotomy-human-descriptions-and-atomic-effects` (revision 1)

Experimental surgery remains a pending Punishment until the actual inflictor selects one to three effects and details, the actual original patient supplies all printed descriptions, and the inflictor completes those saved effects.

Source: rulebook PDF 18 / printed 16; PDF 196 / printed 194

Reason: The text assigns the selections to the surgeon and descriptions to the patient. Generated dialogue or a generic acknowledgement cannot stand in for the patient's actual contribution.

Alternatives: Generate the patient's responses; Resolve the Punishment immediately at type selection; Apply separate partial effects before a recoverable original source exists

Implementation: Source-owned canonical Surgery records preserve all phases and actual participant ActorRefs; no surgery preparation or patient description spends resources or resolves discipline. Actual application is atomic with original debt and bundled causes. Blank name is a source-proved state and clears the Discord nickname via the existing cosmetic queue. Blocked Plays retain actual surgery provenance, including mandatory Plays; the source-specific mandatory no-roll adjudication rule is owned separately by root.

Changing it: Alternative staging must preserve existing patient-authored descriptions, source effects and all unresolved original obligations.

### `actual-frame-consent-voice` (revision 1)

The current human of a represented Core voices it; an unrepresented ordinary NPC Frame is voiced by the current Handler.

Source: Book PDF24/printed22 and PDF68/printed66; digital control clarification

Reason: The source requires consent without naming the human for each ordinary Frame. A represented Core has its own actual identity.

Alternatives: Let the Pilot consent for the Frame.; Let the Handler override represented Cores.

Implementation: Use controller_or_handler. A dead or captured represented Core does not transfer authority. Consent is original subject and Frame bound, one use; opening, extraction and healing remain separate actual operations.

Changing it: Review unfinished exact consent requests before changing authority; preserve original bodies, injuries and source histories.

### `defeat-next-off-duty-frame-replacement` (revision 1)

A surviving Girl with a Frame destroyed by Defeat proposes its different free replacement during preparation of the next actual Off-Duty period.

Source: Book PDF29/printed27; explicit owner different Frame, free charge and Handler-defined package decisions

Reason: The source says next time off-duty without defining a software phase. Real period preparation permits the new Frame before required scenes while preserving delayed source ownership.

Alternatives: Replace immediately in battle.; Delay the package until after the period roll.

Implementation: Transfer the original obligation to a new actual period task with immutable original Frame proof. Handler quotes the exact free package, player confirms, external Court recipient consents. Preserve Girl resources and factual old placement.

Changing it: Review outstanding destroyed-Frame obligations before changing timing. Never grant duplicate packages or rewrite saved source histories.

## Parallel shared-Play, Void and restoration clarifications

All entries below use the owner's delegated recommendation authority and require later printed-rule clarity review. They do not grant player consent, certification or runtime availability.

### `handler-new-persona-starting-npc-relationships` (revision 1)

Every post-death Handler is a fresh source-bound persona. Insurgent may propose Personal starting Bonds to selected actual living known NPCs; their actual controllers explicitly accept the exact shared history, including when the Handler and NPC share one human. No old body Bond transfers or invented NPCs.

Source: Book PDF135 / printed p.133; seven printed Handler starting packages; owner delegated recommendations and source-owned original-body preservation

Reason: The Insurgent selects NPC Bonds without specifying digital establishment or post-death replacement relationships. A prospective persona ID and global body-generation token separate the new original from the GM account and appointment. Exact controller agreement makes the printed starting package usable without transferring archived relationships or silently accepting another role.

Alternatives: Require prior established new-persona NPC Bonds before creation, leaving new Insurgents unable to start.; Reuse dead Handler NPC relationships by account ID.; Spawn NPCs or establish relationships without actual controller agreement.

Implementation: Only an initial persona with no Handler archives globally may adopt existing legacy Handler(None) relationships. Later creation is generation-bound to the latest global Handler archive source event. Old saved or unsaved forms and old persona IDs cannot activate a replacement. Selected Surveilled and Sympathizer labels may overlap; one shared relationship is proposed per actual NPC. Creation creates no transport, NPCs or vehicles.

Changing it: Apply changes prospectively to new proposals. Preserve archived originals, accepted source events, historical Tag setters and explicit human decisions; changing defaults must not rebind historical Bonds.

### `mandatory-forbidden-play-manual-adjudication` (revision 1)

If actual experimental surgery removes the ability to roll a mandatory Defeat, Go Off-Duty or Void Observation Play, keep the inability and await an explicit current Handler decision assigning its complete integer total before actual Tag choices.

Source: rulebook PDF 18 / printed 16; PDF 27–29 / printed 25–27; PDF 196 / printed 194. The resolution of this conflict is a campaign ruling, not an explicitly printed exception.

Reason: Preserves both the actual prohibition and the source-mandated consequence without manufacturing dice, restoring the removed ability, generating a favorable result, or permanently deadlocking the campaign.

Alternatives: Leave mandatory consequences permanently blocked; Restore the forbidden ability without a source; Automatically choose a favorable outcome or invent dice faces

Implementation: The actual original prohibition is proved against its completed surgery event. The mandatory source is proved against pending original Defeat work/response or the actual original's active Off-Duty period. Freeze Handler persona and original CID; only that actual human Handler supplies an integer and factual reason. The whole pre-Tag total is assigned without RNG, dice faces, Heat/Identity spending, numeric base additions or consumption of next-roll supply bonuses. Keep Void Observation's genuine Status-demotion effect. Normal actual Tag choices and owned downstream outcomes follow. Mark receipts MANUAL ADJUDICATION with the source decision. Voluntary forbidden Plays remain blocked, and no ability is restored.

Changing it: Changing this conflict resolution affects future mandatory adjudications. Existing manual receipts, source prohibitions, actual Handler decisions and resulting owned choices remain immutable audit evidence. Replacing a Handler or original character requires explicit source recovery rather than moving authority to a new person.

### `dive-independent-choices-and-order` (revision 1)

High Dive Deep preserves each printed chooser independently: the Girl chooses one effect and the actual Handler chooses one; the same option may be chosen twice and must apply legally twice.

Source: Book PDF24/printed22; delegated recommendation

Reason: The text gives separate choices but does not prohibit overlap or specify asynchronous digital consequence order. Real table effects must finish before irreversible Void conversion can remove their original recipient.

Alternatives: Require different effects even though the source does not state distinctness.; Permit a first conversion to delete the original character before the second selected effect is applied.

Implementation: Actor then Handler each supplies one source-bound option. Apply both original resource effects and real table responses, then lower Status exactly once for the synchronicity spike and open all real Void thresholds while retaining the root lock. Every repeated effect uses then-current actual resources and a distinct actual source event. External Void overlap semantics remain owned by that subsystem.

Changing it: Changing order or overlap changes pending exact choices and downstream snapshots; review existing original action/step facts before any migration, never reroll or rewrite old human decisions.

### `dive-table-human-ownership` (revision 1)

Dive table decisions belong to the frozen actual source cast controllers plus explicitly joined OOC facilitator, deduplicated by actual human controller.

Source: Book PDF24/printed22; source cast rules; delegated recommendation

Reason: The book says the table answers or decides but does not specify a Discord voting protocol. Every original human must retain an actual choice, and one human controlling two roles does not become two independent voters.

Alternatives: Let the bot or Handler automatically answer for absent humans.; Count each fictional role as a separate table vote.; Apply a majority decision over an explicitly rejecting original human.

Implementation: Each actual table human answers an owned question request. For a replacement Identity, the actual Handler coordinates a concrete ordinary-slot/new-label proposal; every frozen human accepts or rejects that exact revision. Rejection requires a new proposal and discards old approvals. Protected extras/Paired slots remain protected in this ordinary-Identity workflow. Full escaped source questions/proposals are paged privately before response. NPC-controller Tag modifier ownership is a separate source-role integration, not inferred from controller UID.

Changing it: Changing table membership or approval semantics affects pending original requests. Do not transfer a response across CIDs, Controller roles or Handler appointments, and do not synthesize approval for a missing human.

### `dive-concrete-details-and-nearby-context` (revision 1)

Affected original Girl owns Asset rewrite/ordinary Identity details; the actual Handler owns each nearby NPC manifestation. An effect must have actual applicable source resources or context.

Source: Book PDF24/printed22; Void PDF19–20/printed17–18; delegated recommendation

Reason: The source assigns option selection but leaves digital detail ownership and nearby distance unspecified. A descriptive empty outcome must not stand in for missing mechanics, and known actual co-presence must not create movement or extra NPCs.

Alternatives: Let the option selector overwrite every private recipient detail.; Invent a fixed numerical radius or new nearby NPCs.; Record empty-target radiation as completed NPC corruption.

Implementation: The original Girl chooses its actual uncorrupted Asset and rewrite or actual ordinary Identity and question. For NPC radiation, affect every living NPC proven same actual cell or actual frozen cast co-presence; the Handler chooses one of four printed manifestations for each. Require at least one actual NPC, an actual ordinary Identity for identity effects, or actual own-cockpit occupancy for subsumption; fail before RNG if no option can apply. Frame Plays remain legal outside the Frame otherwise. Mockingbird Risk Factor uses actual own occupancy, including inside_frame without piloting, and current rule ownership.

Changing it: Changing proximity/detail ownership requires prospective selector changes and review of pending source choices. Existing positions, protected Identities, Asset damage and source NPCs must not be reset or invented.

### `shared-tag-original-source-role` (revision 1)

A Tag marker selects one actual original controlled role; Bond bonuses use that ActorRef rather than its Discord controller ID.

Source: Book PDF11/printed9; Personal/Intense Bond rules; explicit owner ±2 ruling; delegated digital interpretation

Reason: One human can control a Girl and NPC or several NPCs. Numeric NPC IDs and controller accounts are distinct namespaces, so their relationships cannot be substituted for each other.

Alternatives: Use the controller UID for every NPC Bond modifier.; Let a second controlled role bypass the rolling human’s printed self-mark restrictions.; Require an extra visible selector even when only one actual role exists.

Implementation: Freeze original source cast roles/controllers and actual facilitator. Native multiple-role windows require an explicit role picker; a single proved role remains implicit for existing Game.respond callers and is invisibly hash-bound in native UI. Validate the actual original role, resource hash and graph Bond depth/bonus; unknown or changed roles fail closed. Original Girl self-mark exceptions remain required and a second owned NPC cannot proxy them. Reopen only the actual stale human proposal, preserving dice and committed Heat. Store applied ActorRef/source hash privately; do not expose hidden user-named NPC IDs through generic public modifiers.

Changing it: Changing role selection or bonus ownership affects pending exact proposals. Review original cast/controller/ActorRef and graph evidence; never adopt controller Bonds, transfer character authority, reroll dice or infer another human response.

### `shared-tag-mixed-role-discussion-privacy` (revision 1)

When competing Tag proposals include a role with no printed Girl Status, actual original table humans resolve the choice through explicit unanimous discussion without a numeric Status surrogate.

Source: Book PDF11/printed9; prior scene_unanimous_discussion ruling; delegated native protocol

Reason: The source permits Status, discussion or rock-paper-scissors. NPC/controller UID ranking would fabricate Status, while automatically accepting the coordinator’s proposal would manufacture a human vote.

Alternatives: Treat NPC controllers as their own Girls for Status priority.; Let a coordinator decide for all humans.; Reveal every private Tag/relevance or hidden NPC name to the entire table.

Implementation: Keep existing Status priority for actual ranked Pilot/Handler-only proposals. Mixed non-Status proposals use actual coordinator selection followed by every frozen table human’s own acceptance/rejection, including coordinator. Rejection discards old approvals before a new exact candidate. Non-witnesses see only a masked proposal/modifier; Tag label and relevance stay with original witnesses and affected owner, hidden role names stay with controllers or revealed roles. Page full escaped owned text before native agreement. Apply one actual Tag once, only after current source validation and actual discussion; source graph changes invalidate the original bonus snapshot.

Changing it: Changing discussion or privacy semantics requires reviewing pending original-source proposals and approvals. Never add observers automatically, synthesize votes, expose unrelated private sheets or use stale approval for a different source actor/bonus.

### `shared-tag-ooc-facilitator-after-handler-death` (revision 1)

The original human GM can continue the printed other-player Tag window after their fictional Handler dies. An explicit OOC marker has no fictional body, Bond bonus or Status priority and can grant only the ordinary one-point modifier.

Source: Book PDF11 / printed p.9; actual Handler body-ending rule; delegated original-persona protocol

Reason: The human GM and their fictional Handler are distinct. A body ending must archive its original Bonds and authority without stranding the same original table human in Pass or discussion controls. Using a new Handler persona would transfer original authority.

Alternatives: Require a new persona before the human GM can Pass.; Use the dead body or new persona Bonds and Status.; Allow only Pass and omit the printed other-player Tag option.

Implementation: Use Marker.actor=null with enforced depth0/bonus1. For legacy windows prove the original GM body from the actual Play-confirmed event and canonical history. For mixed contexts preserve the exact frozen table/facilitator and accept only the original archive-proven Handler role removal; arbitrary cast changes remain stale. A later persona never replaces the old source role. Competing OOC/role proposals use explicit actual-human discussion without Status ranking; observed-Tag privacy and self-mark restrictions stay in force.

Changing it: Review pending exact role snapshots and actual source body endings before changing this protocol. Preserve original roll/Heat, graph history, human votes and private Tag witnesses.

### `temporary-requisition-benefit-deferral` (revision 1)

Temporarily revoked, earned but unspent Requisition benefits leave the old period's scheduling as deferred, then transfer to a real active period after original inflictor confirmation and original owner restoration. They are never marked consumed or declined by that transfer.

Source: Book PDF17 / printed15 temporary Revoked Privileges; PDF16 / printed14 Requisitions; delegated recommendation

Reason: A restoration condition such as next mission would otherwise permanently block the current Off-Duty period or force forfeiture of a paid benefit. Deferral preserves both the temporary condition and original payment/earned roll without creating currency or rerolling known dice.

Alternatives: Block the original period until restoration, which can deadlock a next-mission condition.; Force permanent paid-benefit decline to progress.; Waive the original inflictor condition automatically.

Implementation: Append-only old work resolution requisition_temporarily_suspended then requisition_benefit_transferred; new actual period work retains original purchase, actor CID, raw roll, action and total plus restoration source. Clear incomplete old scene consent; retain actual fully attested Creature Comforts scene. No new benefit to replacement characters. Personal Firearm restores same confiscated actual item, or only entitlement if already lost; original Frame/grant remains mandatory.

Changing it: Review outstanding deferred and transferred work before changing scheduling. Never retroactively treat transfer as actual consumption, decline, refund or a new qualifying roll.

### `optional-frame-swap-baseline-retention` (revision 1)

A paid optional Frame Swap selects a different official Frame playbook, uses its normal two chosen starting Assets and printed setup/extras, and retains exactly one actual old Frame Asset plus one actually unlocked old Frame rule. It costs four Permissions and never uses the compulsory replacement package.

Source: Book PDF16 / printed14, destination starting playbooks PDF61/65/68/71/74/78/81/84/88; delegated recommendation

Reason: New Frame Playbook supplies its normal starting baseline; the printed retained Asset and rule are the additional explicit carryover. Existing Girl resources and actual item ownership do not disappear because her assigned machine changes.

Alternatives: Permit repeated exchange into the same playbook.; Treat retained items as the entire new baseline rather than additional carryover.; Use the compulsory Handler-defined free replacement package for a paid swap.

Implementation: Price4 at final atomic owner payment after actual new Frame delivery at the unchanged body location. Exact original Court recipient must accept. New CONSUME Quiet/Doctor0 use already approved campaign defaults. New Changeling strings bind actual existing Bond counterparts. Old Frame is source-archived parked, never fake-scrapped. Actual Girl pistol remains the same item; retained Firearm rule transfers future lost-item entitlement without reissue. Wyvern Enormous's extra-cap treatment is a native base rule, not silently carried with the Asset alone. Already completed historical exchange is not revocable currency or a reversible time operation; selectors expose only currently held removable benefits. Unimplemented/review-pending native baselines and retained-rule consumers remain gated.

Changing it: Changing baseline/retention requires reviewing actual existing new Frames, paid receipts and parked old Frames; no automatic charge/refund, item duplication or context rewrite.

### `enforcer-factual-rank-innocence` (revision 1)

An Enforcer's NPC superior-officer exception uses an explicit current Handler factual rank declaration relative to the original Girl. Foundation detention persists until actual current Handler evidence establishes innocence; ending the accuser's career does not erase Foundation custody.

Source: Book PDF78 / printed76 Obedience Conditioning; delegated implementation interpretation

Reason: NPC playbook jobs do not establish military rank. The printed arrest is a real custody consequence, not proof of objective guilt or forced belief by the Handler. Releasing custody does not establish where the original body physically is.

Alternatives: Assume all NPCs except Directors are subordinate.; Let the accuser choose whether the target is superior and when innocence is established.; Restore the NPC to a stale map location automatically.

Implementation: Original rank/accusation ActorRefs and actual state/event proofs. Detained NPC may participate in actual prison roleplay; only unsupported escape/movement is blocked. Current cell unknown through custody and after release until one concrete sourceful factual map declaration. No new prison coordinate, counterfactual extraction or timer. Production full Obedience gate remains closed until trust/volunteer consumers and independent review actually complete.

Changing it: Review outstanding actual NPC custody and source-bound cases before changing rank or innocence authority; preserve original evidence and do not move bodies as a policy side effect.

### `void-family-overlap` (revision 1)

When full Girl and Frame corruption are pending together, retain both exact sources, resolve actual Frame enclosure first, and preserve full-Girl allure after a real escape.

Source: Book PDF 19, 179; delegated source reconciliation

Reason: The book gives both conditions without a simultaneous-effect order. A successful printed escape must not erase the remaining corruption or duplicate the same physical body.

Alternatives: Require completed Harpy transformation before allowing the Frame escape.; Create independent competing physical transformations.

Implementation: Consumers: engine.m3_void.start_threshold, services.m3_void.prepare_threshold, services.m3_physical.PhysicalService.operate. Scope: implemented_under_delegation. This interpretation does not enable missing consumers.

Changing it: One actual damaging escape and one original Frame Gorgon; Girl remains her original body/resources. Canonical allure persists, and actual entry into a future assigned Frame opens a new source-backed threshold.

### `void-outside-frame` (revision 1)

If the Girl is actually outside her affected Frame, do not enclose, move or damage her to manufacture an escape. The Handler gives the actual original Frame its Gorgon form at its existing known or unknown position.

Source: Book PDF 19, 24; delegated source reconciliation

Reason: Basic Frame Plays explicitly work outside the Frame, while the corruption paragraph assumes enclosure. Preserving the separate actual body and applying Frame transformation is the least added effect.

Alternatives: Defer all Frame transformation until actual entry.; Charge an escape injury even though she was never enclosed.

Implementation: Consumers: engine.m3_void.abandoned_frame, engine.m3_void.confirm_occupancy, discord_adapter.m3_void.open_void. Scope: implemented_under_delegation. This interpretation does not enable missing consumers.

Changing it: Original Girl position, vessel, injuries and resources stay unchanged; actual Frame Assets retain identities/damage in the Gorgon. Unknown occupancy first receives owned factual proposal plus independent Handler confirmation.

### `void-involuntary-frame-loss` (revision 1)

Actual involuntary Frame abandonment into a Gorgon creates a genuine compulsory replacement at the next actual Off-Duty preparation, using the already approved free, Handler-defined, different-Frame package.

Source: Book PDF 19, 16, 29, 71; delegated source reconciliation

Reason: The source requires a functioning assigned Frame for the ordinary loop but gives no separate price for this loss case. It should not falsely become a destroyed-Frame fact or a paid optional Frame Swap.

Alternatives: Require purchasing the optional Frame Swap.; Leave the original Girl permanently unable to enter the next period.

Implementation: Consumers: services.m3_void.complete, services.m3_defeat_replacement. Scope: implemented_under_delegation_root_replacement_bridge. This interpretation does not enable missing consumers.

Changing it: One deterministic campaign-scoped void_frame_replacement source, no Permission charge, actual Gorgon preserved and no Girl healing/resource reset. The replacement bridge is owned by root.

### `void-actual-arrival` (revision 1)

The original owner proposes actual completed stage-one arrival/embrace and selects the Identity to become Free; the current Handler independently confirms actual facts when existing positions differ or remain unknown.

Source: Book PDF 179, 19; delegated source reconciliation

Reason: Stage one explicitly describes making her way to and entering her Frame. An acknowledgment must not teleport a body, and a distant or unknown position must not make the printed transformation impossible to complete.

Alternatives: Require already recorded same-cell positions for every transformation.; Automatically relocate the Girl without an actual arrival source.

Implementation: Consumers: engine.m3_void.confirm_approach, services.m3_void.VoidService.respond, discord_adapter.m3_void.open_void. Scope: implemented_under_delegation. This interpretation does not enable missing consumers.

Changing it: Exact original body/Frame and current state are frozen; intervening changes require reproposal. Actual known Frame position becomes the entered body position, or coordinates remain unknown. No new vessel, healing or ordinary travel command is created.

### `void-guardian-control` (revision 1)

Actual protection requires the original request and a separate response through the controlled actual guardian role. Only that role controller releases its still-active hold. An actual guardian career end interrupts its source-created hold without moving or healing the protected body.

Source: Book PDF 19; delegated source reconciliation

Reason: A mere acknowledgment is not physical prevention; lasting custody needs an actionable way to end and must not become inherited authority for the guardian controller’s next character.

Alternatives: Count a player acknowledgment as prevention without a physical consequence.; Create an indefinite hold with no owned release or ending cleanup.

Implementation: Consumers: engine.m3_void.prevent_entry, engine.m3_physical.release_protective_hold, engine.m3_physical.interrupt_protective_holds, engine.m3_physical.interrupt_journeys, services.m3_void.VoidService.respond. Scope: implemented_under_delegation. This interpretation does not enable missing consumers.

Changing it: Shared actual cast/immutable legacy-cast evidence is required; known separated cells cannot become co-location, and unknown positions stay unguessed. Resolved-source card remains in the inbox while the hold is active. Girl allure persists, so later actual own-Frame entry re-triggers. Actual NPC/Harpy death consumers must invoke the exported interruption helper.

### `harpy-free-identity-reconciliation` (revision 1)

At birth replace the selected actual Identity label with Free, preserving real marks/locks. At rebirth retain only the old resources the owner chooses, then add the additional distinct Free from Harpy starting rules.

Source: Book PDF 179, 181; delegated source reconciliation

Reason: PDF179 replacement/erasure and PDF181 additional-Free starting text are not fully aligned. This is a literal two-stage reconciliation, not an unambiguous printed result.

Alternatives: Coalesce a retained Free into one additional non-ordinary Identity.; Use only PDF179 and make no additional Free compulsory.

Implementation: Consumers: engine.m3_void.begin_questions, engine.m3_void.confirm_approach, engine.m3_void.rebirth, engine.m3_void_state.HarpyIdentity. Scope: implemented_under_delegation_requires_clarity. This interpretation does not enable missing consumers.

Changing it: A retained birth-Free and the final additional Free may have the same label but distinct IDs. Harpy Identities have no ordinary four-slot cap. This affects the available pool of markable Identities and must be easy to revise.

### `harpy-bond-retention` (revision 1)

A former PC Harpy retains the original fictional person’s Bonds except those the original owner actually discards during rebirth; preserve exact counterpart ActorRefs and rebind the same person to the actual new Harpy body.

Source: Book PDF 179, 181; delegated source reconciliation

Reason: The explicit permission to discard unwanted Bonds and the former-PC retention rule can coexist. Human account IDs and a successor Girl are not the same fictional endpoints.

Alternatives: Erase every former PC Bond at conversion.; Copy numeric account edges onto a replacement Girl.

Implementation: Consumers: engine.m3_void.rebirth, engine.m3_actor_bonds.migrate_actor, engine.m3_actor_bonds.rebind. Scope: implemented_source_reconciliation. This interpretation does not enable missing consumers.

Changing it: One canonical ActorRef graph, no duplicate numeric authority, no inheritance by a new Pilot incarnation. Original Harpy retains independent Heat/resources and controller.

### `harpy-overgrown-survival` (revision 1)

Any honest yes leads to actual consumption/overgrowth. The actual Handler records uncertain survival as a real factual outcome; neither death nor survival is silently assumed.

Source: Book PDF 179; delegated source reconciliation

Reason: The text explicitly says likely but not certainly dies, without a roll or numeric procedure.

Alternatives: Always kill the Girl automatically.; Always grant survival automatically.; Invent an unsupported survival roll.

Implementation: Consumers: engine.m3_void.answer_question, engine.m3_void.overgrown_fate, services.m3_void.VoidService.respond. Scope: implemented_under_delegation. This interpretation does not enable missing consumers.

Changing it: A living original Girl remains the same injured/incapacitated body inside the actual Gorgon Frame and in its custody; no reborn Harpy, extraction, healing or medical help is invented. Actual death archives the original. Future real rescue/medical recovery remains required.

### `mockingbird-outside-frame-corruption` (revision 1)

Current corrupt reducer emits Mockingbird resistance only when she is actually in her own Frame with all Frame Assets Void. Outside, no autonomous Frame-Gorgon work is emitted; real later entry creates source-backed resistance.

Source: Book PDF 19, 35; delegated source reconciliation

Reason: Risk Factor explicitly restricts when the Girl succumbs, but whether that also postpones autonomous Frame transformation is unclear. Do not describe the current behavior as unambiguous source text.

Alternatives: Apply autonomous Frame-to-Gorgon outside while preserving the Girl’s Risk Factor immunity.; Apply the exception to both Girl and Frame until actual entry, matching current code.

Implementation: Consumers: engine.m3_core.corrupt, engine.m3_void.start_threshold, services.m3_physical.PhysicalService.operate. Scope: current_behavior_ambiguity_review_not_new_implementation_claim. This interpretation does not enable missing consumers.

Changing it: Changing this choice changes the availability of the original Frame before re-entry and requires a real Frame transformation consumer/test, not merely a documentation or policy flag.

## Handler body and continuing human GM authority

Delegated recommendations, all requiring printed-rule clarity review.

### `handler-fictional-body-and-human-gm-separate` (revision 1)

Actual Handler death ends the fictional body; the same appointed human continues OOC adjudication and may create a fresh persona.

Source: Book PDF15 / printed13; Handler body/context continuation is a delegated campaign implementation interpretation

Reason: Fictional death must retain its resource consequences without stranding mandatory human decisions.

Alternatives: End the human appointment or treat the dead body as alive.

Implementation: Archive exact body, Tags, Heat, Bonds and source links. Remove its fictional cast role. Freeze actual human GM and appointment separately from the optional historical body; no fictional ability, consent or Bond/Status bonus follows from OOC authority.

Changing it: Review pending original-body decisions; retain actual deaths and human decisions.

### `handler-fresh-persona-no-predecessor-inheritance` (revision 1)

After any Handler body archive, fresh creation uses a new generation and fresh owned starting choices, with no predecessor resources, authority or consent.

Source: Book PDF15 / printed13; Handler body/context continuation is a delegated campaign implementation interpretation

Reason: A Discord account is not the fictional person; first legacy adoption names the existing same body only.

Alternatives: Reuse old persona forms/resources or forbid replacement entirely.

Implementation: Allow initial legacy adoption only before any archive. Derive subsequent generation from the real ending event; stale drafts/forms/agreements cannot activate. NPCs remain distinct controlled people, not inherited Handler abilities.

Changing it: A different baseline needs explicit future policy and migration; never transfer historical personal rights silently.

### `handler-death-terminates-director-context-without-departure` (revision 1)

Handler death suspends the original Director-presence context and source-proved old-body reviews without NPC departure or departure rewards.

Source: Book PDF15 / printed13; Handler body/context continuation is a delegated campaign implementation interpretation

Reason: The dead body cannot continue Girl-rule Identity use, while death does not prove the Director left.

Alternatives: Run ordinary departure effects or transfer the old context to a fresh persona.

Implementation: Archive the original context. Preserve actual Director and Identity records; set inactive with actual death termination event and revision. Close only reviews proven to concern the original body. A new persona requires a fresh actual context.

Changing it: Preserve original presence and nondeparture proof; apply future recovery changes prospectively.

### `handler-already-dead-pending-damage-sources` (revision 1)

Other pending damage/Helpless replacement requests for an actually dead original Handler end by that death source, without another fabricated selection or successor inheritance.

Source: Book PDF15 / printed13; Handler body/context continuation is a delegated campaign implementation interpretation

Reason: An already-dead original cannot choose a live-body replacement effect; pending sources must preserve actual ownership.

Alternatives: Leave requests permanently pending, assign them to a successor, or manufacture another death choice.

Implementation: Preserve each frozen trigger/opponent/action/work/request. The chosen request records death; other same-body requests record ended and actual ending consequence/event, with no invented choice. Only registered exact source callbacks can finish; unsupported producers fail closed.

Changing it: Retain individual original source events and actual death; review future overlapping-trigger policy explicitly.

The first-Handler creation adoption also updates only open exact legacy Handler roles for that same body, with the actual activation event and a new cast revision. Closed cast history stays intact. No activation after a Handler body archive adopts an old role or its consent. This implements `handler-starting-creation-ownership` and does not change the fresh-persona ruling.

## `go-for-core-target-branches-and-owned-decline`

On Go For the Core 11+, anyone else means non-NPC target categories, not automatic bystander damage. Every target may choose its owned counter, including a dying NPC; an explicit decline is permitted by may.

Source: Book PDF26 / printed24; NPC distinction PDF5; delegated literal interpretation

Reason: The paragraph contrasts the target being an NPC with other target categories. Applying automatic damage to every bystander invents effects. The preceding target counter permission is not expressly removed for NPCs; may permits an actual owned decline.

Alternatives: Damage every bystander automatically and omit the NPC counter.; Require a target counter even when its original controller explicitly declines.

Implementation: High: actual NPC explosive death; non-NPC target damages an actual undamaged Asset or dies. Both retain an actual optional zero-or-one counter; low permits explicit decline or one-to-two counters and actual NPC defense/death proof. Never infer decline from absence or grant another role the choice. Default Handler gear descriptions create no Assets: no real undamaged Asset means death. Only source-proved actual transferred mechanical items may supply an Asset consumer; no proxy sheet or HP slots.

Changing it: The earlier unimplemented foundation plan was corrected. Actual battle consumers and golden traces must use this scope; preserve known outcomes and review any future source clarification before changing pending counters.

Delegated recommendation; printed-rule clarity review remains required. The battle runtime is still in development; this record alone does not enable it.

## Source-bound combat, original-person and Harpy clarifications

These use the owner's delegated recommendation authority and remain flagged for printed-rule clarity review. They do not certify missing implementations, give player consent, enable optional Ancillary rules, or change live policy. Full rationale, alternatives, revision and change impact are retained in `rules/registry.json`. Changing an interpretation requires reviewing its pending source-bound work; preserve actual receipts and immutable history.

### `gm-ooc-tag-setter-principal`

A Tag deliberately authored by the actual human GM uses that original human and frozen authenticated appointment as setter, independently of any fictional Handler body. No future persona gains this authorship.

Source: Book PDF115 / printed p.113 (GM responsibility while not actively playing the Handler character); PDF117 / printed p.115 (Mess with Status, Tags or Assets); PDF11 / printed p.9 (Tags); delegated digital source-ownership interpretation.

Reason: The ordinary Handler Play remains a human GM procedure when the GM has no fictional Handler body. Assigning its Tag to the giver UID current persona would fabricate a body or transfer authorship after replacement. The original human owns their actual authored choice; fictional setter Tags remain source-ActorRef-bound.

Alternatives: Require an actual Handler body for the ordinary GM procedure.; Treat the current persona as original setter by matching account UID.; Allow an arbitrary appointment string to assert OOC ownership..

Implementation/adjustment: New OOC Tags require actual Game event actor matching authenticated GM appointment and record gm_setter_appointment plus actual gm_setter_event. The source-proof helper validates actual creation history, original target CID/body/context, unchanged original Tag principal, actual appointment at creation, and absence before creation. First persona adoption and body-ending stamps skip OOC Tags. Such a human Tag does not qualify for character-specific Mentor exceptions. Preserve these fields across actual Void conversion without fabricating an ActorRef. Do not relabel existing fictional Tags or infer OOC authorship from a missing legacy ActorRef. Historical Tags need actual original source proof; changing principal requires explicit source review and cannot transfer old consent to a new persona.

### `battle-core-relevant-vessel-assets`

Count only actual undamaged Assets belonging to the target and physically present with that targeted body: outside or unlinked Girl/Harpy Girl Assets only; own linked Frame includes its Frame Assets; passenger excludes assigned parked Frame and carrier resources; real mechanical held objects retain source identity.

Source: Book PDF 15, 26, 113, 178; delegated recommendation.

Reason: Remote or another person’s resources cannot provide invisible armour or be damaged through the wrong body.

Alternatives: Literal all owned Assets including remote parked Frames; Count carrier armour as passenger resources.

Implementation/adjustment: Outside/passenger Core modifier changes; actual carrier Core exposure remains required; no body travel, resource reassignment or controller alias. Outside/passenger Core modifier changes; actual carrier Core exposure remains required; no body travel, resource reassignment or controller alias. Review pending source work before revision; preserve original receipts and immutable history.

### `battle-high-fixed-cost-snapshot`

Freeze the high result fixed damage/death predicate and eligible original Asset IDs when the counter window opens; perform actual counter effects before payment; a newly evolved/repaired additional Asset or closed Core cannot negate an already required death or pay with a newly created Asset.

Source: Book PDF 26, 162; delegated recommendation.

Reason: Keeps counter ownership and last actions real while preserving the printed fixed strike cost and original actual target.

Alternatives: Recompute after every counter effect, allowing new survival resources; Apply death before counters and infer archived ordinary abilities.

Implementation/adjustment: Deferred real original-body effects; no new-body damage or duplicate death if original ended during its own counter; original controller can explicitly decline optional counters. Deferred real original-body effects; no new-body damage or duplicate death if original ended during its own counter; original controller can explicitly decline optional counters. Review pending source work before revision; preserve original receipts and immutable history.

### `battle-handler-gear-is-not-slots`

Description-only Handler gear grants no numerical Assets or HP. Only a proved actual mechanical HeldItem supplies an Asset. A baseline Handler has Core modifier zero and the printed direct death on mid or high without actual undamaged Assets; actual would-damage or Helpless uses its owned replacement choice.

Source: Book PDF 15, 26, 124; delegated recommendation.

Reason: The source gives gear access and a replacement table, not a hidden numeric sheet.

Alternatives: Infer one Asset for each named weapon or outfit; Always replace decisive death with an injury choice.

Implementation/adjustment: No invented HP; no Handler injury escape from explicit decisive death. Girl-rules context actual object damage is a separate body resource port. No invented HP; no Handler injury escape from explicit decisive death. Girl-rules context actual object damage is a separate body resource port. Review pending source work before revision; preserve original receipts and immutable history.

### `battle-director-actual-body-rules`

The Director remains its actual NPC identity but consumes Handler-rule damage/Helpless replacement choices. Real death ends only that body, cast role and affected presence; actual other living participating Directors preserve the Handler’s context. A required new Director has a new ID and a real separately accepted human role.

Source: Book PDF 15, 26, 192; delegated recommendation.

Reason: The explicit Director rule overrides ordinary NPC mechanics; his controller is not silently the appointed GM or another person’s Handler body.

Alternatives: Ordinary NPC replacement/explosion mechanics; Alias Director to main Handler resources; Automatically spawn an unaccepted replacement.

Implementation/adjustment: Dedicated actual-body consequences and source-proved administrative replacement, no fictitious departure, Heat reset or free Identities. Current context body_actor retains stable physical identity through rule changes. Dedicated actual-body consequences and source-proved administrative replacement, no fictitious departure, Heat reset or free Identities. Current context body_actor retains stable physical identity through rule changes. Review pending source work before revision; preserve original receipts and immutable history.

### `battle-npc-defense-existing-source`

An ordinary NPC low-result defence must be an actual held object, recorded capability Tag, or real protective location already present in canonical history before the attack declaration, with the GM confirming its actual relevance before dice.

Source: Book PDF 26, 188, 189, 190, 191; delegated recommendation.

Reason: The book allows a way to defend oneself but does not give NPCs automatic immunity or an after-result invented shield.

Alternatives: Assume every guard is immune; Create a defence after learning a failed strike; Never permit NPC defence.

Implementation/adjustment: No invented stats; actual owner still chooses optional counters. Real defence does not prevent the fixed high-result NPC death. No invented stats; actual owner still chooses optional counters. Real defence does not prevent the fixed high-result NPC death. Review pending source work before revision; preserve original receipts and immutable history.

### `battle-npc-conversation-counter`

An NPC may perform an exact owned job-defined Conversation move as its counter, with its actual action recorded against the original attacker. The implemented narrative move subset creates no invented HP, player replies or general GM authority.

Source: Book PDF 188, 189, 190, 191; delegated recommendation.

Reason: The NPC chapter explicitly describes these Plays as Conversation guidelines, rather than another dice system.

Alternatives: Replace NPC Play with GM Play; Treat any handled acknowledgement as completion.

Implementation/adjustment: Safe source moves are available for most jobs; mechanical job moves and full job playbooks remain separately scoped and are not claimed complete. Safe source moves are available for most jobs; mechanical job moves and full job playbooks remain separately scoped and are not claimed complete. Review pending source work before revision; preserve original receipts and immutable history.

### `battle-scene-director-judge`

The actual campaign GM records factual pre-roll opening/reach review and procedural table input. When a Director is present in the actual scene, an explicit self-owned cast adjudicator must be selected; its actual controller owns frozen Battle result and forced Handler-rule choices for this episode.

Source: Book PDF 25, 26, 192; delegated recommendation.

Reason: Separates OOC campaign administration from fictional/printed Director authority without moving another body or giving global GM permission.

Alternatives: Let the main Handler choose despite Girl-rules mode; Automatically appoint a Director without a real source choice; Treat the Director controller as a new global GM.

Implementation/adjustment: Context freezes actual Director ActorRef/controller and signed role selection; original episode authority survives source completion, and new bodies/other characters gain no general permission. Context freezes actual Director ActorRef/controller and signed role selection; original episode authority survives source completion, and new bodies/other characters gain no general permission. Review pending source work before revision; preserve original receipts and immutable history.

### `battle-core-damaged-actual-asset-capability`

Go For the Core still requires a real owned mechanical Asset. A damaged Asset may be declared only when actual pre-roll Conversation explicitly confirms that this damaged Asset can perform the strike; ordinary objects or invented body capability do not create Assets.

Source: Book PDF 15, 26; delegated recommendation.

Reason: PDF26 explicitly requires saying what Asset is used; PDF15 permits fighting with Plays but conditions Conversation use on an undamaged Asset. The damaged-Play eligibility needs clarity rather than a fabricated zero-Asset exception.

Alternatives: Require undamaged Assets for all combat Plays; Allow every damaged Asset automatically; Allow nonmechanical gear or a zero-Asset body strike.

Implementation/adjustment: Context records an actual procedural source confirmation before RNG; the printed Asset requirement and actual custody remain enforced. All Out Assault damaged-Asset permission is not implied. Requires printed-rule clarity review. Context records an actual procedural source confirmation before RNG; the printed Asset requirement and actual custody remain enforced. All Out Assault damaged-Asset permission is not implied. Requires printed-rule clarity review. Review pending source work before revision; preserve original receipts and immutable history.

### `enforcer-grip-contact-source`

Freeze whether the actual taking hold used the Girl body or her piloted original Frame; reject known contradictory contact positions and leave unknown cells unknown.

Source: Book PDF79 / printed77; physical context PDF113 / printed111.

Reason: The trigger does not impose a universal piloting-only requirement or supply teleportation. Earned grip belongs to its actual physical source; losing a Frame ends a Frame-contact grip, while the same living original Girl can always release a body grip.

Alternatives: Restrict all such grips to piloting without a printed restriction.; Treat all grips as persistent after the actual holding Frame is destroyed..

Implementation/adjustment: Original holder release is pause-safe and does not move anybody or cure separate Helplessness. Optional Frame Swap, reserve and Retirement block outstanding grips. Actual compulsory loss/replacement does not transfer grip to a new Frame. Review historical Grasp.contact sources before changing classification; never invent a retroactive physical position.

### `enforcer-volunteer-preserves-chooser`

A non-Dog Enforcer may offer to carry out a real pending Punishment; the original chooser accepts an actual executor while retaining the debt and instruction ownership.

Source: Book PDF78 / printed76; Punishments PDF17–18 / printed15–16.

Reason: Volunteering is an offer rather than an automatic reassignment or fulfillment. This keeps the printed inflictor resources/Bonds attributed to the actual executor and preserves the original source obligation.

Alternatives: Automatically transfer the original selection ownership to the volunteer.; Treat offering as completion of the Punishment..

Implementation/adjustment: Decline/withdraw closes only optional offers. Actual on-screen participation, actual type/details, Handler consultation where needed, actual effects and immediate followups remain required. Unsupported severe/delegated surgery execution is unavailable, never represented by proxy authority. Outstanding offers retain original ActorRefs and source work. Do not reopen fulfilled debt or transfer an old incarnation to its successor.

### `enforcer-original-body-ending`

If an actual printed Handler replacement or source-bound Void outcome ends an original participant before later Initiative clauses can occur, record the actual ending and explicitly unperformed clauses; do not punish or question a replacement body.

Source: Book PDF15,19,79 / printed13,17,77.

Reason: The printed rules do not explain this overlap. An actual death/conversion cannot manufacture the original on-screen scene or silently grant an entitlement over a new person.

Alternatives: Require a fabricated acknowledgment of impossible old-body scenes.; Transfer the old consequences automatically to a new character/persona..

Implementation/adjustment: Only actual source-event archives/final Void outcomes authorize closure. Known rolls are retained; no refund, reroll, fake response, new persona or invented Punishment is produced. Audit completed original-source closures separately from fulfilled Punishments. This interpretation explicitly requires printed-rule clarity review.

### `held-object-source-eligibility`

Girl Asset ownership alone does not classify a body part or trait as a takeable object. Use printed pistol/Gun sources or actual holder-and-Handler proof of an existing carried object, optionally bound to an unchanged actual Girl Asset.

Source: Book PDF15,79,113 / printed13,77,111.

Reason: Taking something from a person must have a real object source. A descriptive possession is not a newly granted mechanical Asset, while an existing physical Asset retains its real source and mechanical identity.

Alternatives: Offer every Girl Asset, including body parts/traits, as loot.; Grant fresh Asset statistics to every story possession..

Implementation/adjustment: Factual confirmation records no new slots/stats and cannot detach mounted Frame equipment or body parts. Current custody and immutable original ownership remain necessary. Weapon-on-hand is an actual printed or confirmed factual property, not inferred from arbitrary names. Historical object bindings must preserve source ActorRefs/Asset IDs; do not duplicate an object when its original Asset is restored or a new incarnation appears.

### `personal-firearm-foundation-replacement`

A qualifying lost-pistol return is a Foundation-issued replacement physical pistol with a distinct identity, under the same original paid grant and qualifying event.

Source: Book PDF79 / printed77; owner delegated recommendation adopted by root.

Reason: The source permits getting the lost pistol back without specifying retrieval when its original is in another actual person's custody. A distinct Foundation issue preserves truthful physical custody and source-bound eligibility.

Alternatives: Require actual retrieval and custody transfer of the stolen original.; Teleport a stolen original away from its current real holder..

Implementation/adjustment: Record original recipient ActorRef, actual human controller, prior lost Asset ID, actual grant/roll/event and replacement mode. Never duplicate one physical ID or alter the stolen original's custody. Later recovery is a separate real inventory transfer with normal capacity. Audit distinct existing issue IDs/custody before changing the interpretation. No extra ability, Permission currency or unlimited Asset slots is granted. New rulings do not retroactively move original objects.

### `retained-beneath-lock-same-person`

A Tag explicitly retained by the same fictional person through actual Harpy rebirth retains its original Beneath rejection restriction. Only the original locker (including its proved same-person Harpy conversion) grants consent; Tag giver and replacement characters gain no consent authority.

Source: Book PDF22 / printed20; PDF179,181 / printed177,179; delegated source reconciliation.

Reason: Retaining the same Tag does not explicitly revoke its printed lock. Rebirth preserves a fictional person while changing actual actor representation; immutable conversion/retention and original source proof prevent account aliases from changing choice ownership.

Alternatives: Remove every Beneath restriction at Harpy conversion.; Copy old UID consent authority onto replacement Girls..

Implementation/adjustment: Pure engine.m3_tag_permissions verifies actual selected retained IDs and original obligations. PermissionService verifies genuine immutable original effect/real birth/explicit locker command before actual ActorPlay rejection. Marker is recorded only on newly created career archive before first history; no past archive rewriting. Scope: implemented_source_reconciliation; no source review certification. Changing this interpretation affects currently pending retained-Tag consent; append a sourceful adjustment rather than silently rewriting prior grants, birth history or discarded Tags.

### `harpy-frame-human-voice`

The actual Harpy controller voices the actual retained Frame for source extraction permission and opening.

Source: Book PDF 24, 178, 179; delegated recommendation.

Reason: Harpy combines her Girl/Frame; no separate GM/NPC Frame voice is supplied. Requires actual source-bound Harpy/Frame identity.

Alternatives: Require an independently assigned Frame voice, creating an unprinted control assignment..

Implementation/adjustment: No GM permission substitutes; revocation and later positive consent remain explicit actual owned responses. No GM permission substitutes; revocation and later positive consent remain explicit actual owned responses. Review pending source work before revision; preserve original receipts and immutable history.

### `dormant-already-fully-void-harpy`

If every actual Harpy Asset is already Void, explicitly record the actual inflicted Void state with no resource alteration or new Asset; still perform actual forced Dive if source close. If an uncorrupted Asset exists it must be selected and altered.

Source: Book PDF 19, 165, 181; delegated recommendation.

Reason: Gain Void normally rewrites an uncorrupted Asset; an already transformed fully Void Harpy cannot gain a fabricated Asset or repeat conversion.

Alternatives: Block resolution indefinitely or create an additional Void Asset without source authority..

Implementation/adjustment: No free Asset, healing or repeated transformation. Source cost is auditable; forced Dive remains required. No free Asset, healing or repeated transformation. Source cost is auditable; forced Dive remains required. Review pending source work before revision; preserve original receipts and immutable history.

### `harpy-extraction-vitals-separate`

Real extraction with actual Frame consent unlinks the actual Harpy body at the Frame current cell, preserving unknown positions and inactive vital signs. Real medical help must separately establish recovery.

Source: Book PDF 24, 178, 179; delegated recommendation.

Reason: Dive states inactive vital signs and consent gate; neither permission nor physical removal says to heal, transport or revive.

Alternatives: Treat extraction as automatic waking and relocation..

Implementation/adjustment: Owner/help proposals and actual GM factual review preserve resources, locations, source locks and audit. Subsumption alone does not prohibit Frame control. Owner/help proposals and actual GM factual review preserve resources, locations, source locks and audit. Subsumption alone does not prohibit Frame control. Review pending source work before revision; preserve original receipts and immutable history.

### `returned-original-source-work-reissue`

After an actual original-owner return, issue new source-bound pending work rather than reopening a closed original career receipt. A replacement character inherits none of it.

Source: Book PDF16-18,29 and181; delegated digital original-character restoration interpretation.

Reason: Printed obligations and replacement consequences attach to their actual original character. A recorded career ending closes historical work; restoring that person must not erase the still-unfulfilled cause or mutate old receipts.

Alternatives: Reopen and mutate the original closed work.; Discard every unfulfilled cause on return.; Assign the old cause to the same human account's new character..

Implementation/adjustment: Authenticate original closure/archive and latest actual return against immutable history. Reissue only the relevant unfulfilled source family in a new actual period, preserve original character IDs and suppress fulfilled or already-pending descendants. Review outstanding returned-original work before changing timing. Keep fulfilled outcomes, closed receipts, actual return records and successor resources intact.

### `returned-mission-discipline-next-actual-period`

An outstanding original mission cause that survives a genuine return is handled in the first eligible actual Off-Duty period after that mission completes. The same mission failure and Dog cause share one actual Punishment; a separate Defeat cause remains separate.

Source: Book PDF16-18 and29; explicit owner failure/Dog overlap decision plus delegated post-return timing.

Reason: An absent original person cannot receive a staged Punishment through their replacement. Original mission obligations still need a real on-screen resolution once that same person returns; this supplies timing without inventing a second punishment for the owner-approved failure/Dog overlap.

Alternatives: Reopen the completed original mission.; Require discipline before the original has actually returned.; Forgive unfinished causes when a career is interrupted..

Implementation/adjustment: Preserve the first actual mission cause, immutable completed mission and original CID. Bind new actual period work only after source-authenticated return; actual punishment and owned screen attestations settle the debt, with failure/Dog bundled only for that same mission and return. Changing timing requires reviewing pending return work. Never repeat completed Punishments, merge a distinct Defeat debt into failure/Dog, or transfer an old cause to a successor.

### `harpy-defeat-inherited-forbidden`

An actual same-person Harpy retains the original surgery's forbidden Defeat. Its mandatory source opens an explicit owned human adjudication of the whole pre-Tag integer total, without dice, faces, Heat spending or automatic modifier addition. Actual normal Tag and outcome decisions follow.

Source: Book PDF 181, 182, 196; delegated recommendation.

Reason: A same-person transformation does not erase an actual completed surgery. A mandatory consequence still needs a real owned outcome, so the existing clearly labelled no-roll adjudication applies without restoring the forbidden Play.

Alternatives: Ignore the source surgery and roll; Leave the mandatory consequence permanently blocked.

Implementation/adjustment: Extends the existing delegated mandatory no-roll ruling; does not restore an ability or supply a favorable result. Extends the existing delegated mandatory no-roll ruling; does not restore an ability or supply a favorable result. Review pending source work before revision; preserve original receipts and immutable history.

### `harpy-rescue-owned-hard-effect`

The defeated Harpy's original controller selects another actual scene Harpy for the printed rescue. Move the actual accessible surviving bodies to unknown offstage positions without manufacturing the rescuer's human answer or dialogue. Real custody, subsumption and extraction gates still apply.

Source: Book PDF 182; delegated recommendation.

Reason: The printed result grants rescue by an actual Harpy already in the scene, without adding a separate veto or an invented rescuer. Keep the hard result distinct from human-authored dialogue and from physical extraction gates.

Alternatives: Add a rescuer veto not stated by this result; Invent another Harpy or a rescue reply.

Implementation/adjustment: Preserves the printed hard effect and distinct actors/resources. Preserves the printed hard effect and distinct actors/resources. Review pending source work before revision; preserve original receipts and immutable history.

### `harpy-escape-and-navigation`

Printed escape places each actual traveling body and accompanying occupied vessel offstage with unknown position, preserving resources, custody distinctions and parked Frames. Rift following needs an original-controller factual navigation proposal and explicit source adjudicator review. A return needs its actual destination and actual reviewed navigation, without automatic healing or relocation to base.

Source: Book PDF 182; delegated recommendation.

Reason: Escape establishes leaving the present situation, not an arbitrary map destination. Navigation and return therefore require actual original-controller facts and a real adjudicator review while maintaining unknown positions.

Alternatives: Assign an arbitrary map destination; Grant navigation from the Rift alone.

Implementation/adjustment: A typed overlay handles World bodies whose base map cell cannot represent unknown; no second Asset pool exists. A typed overlay handles World bodies whose base map cell cannot represent unknown; no second Asset pool exists. Review pending source work before revision; preserve original receipts and immutable history.

### `harpy-plea-vessel`

Only the actual original Girl answers the plea. Refusal applies her actual Status increase and her chosen Tag. Acceptance preserves her currently piloted own Frame when it actually accompanies her; an outside body leaves its assigned parked Frame in place. Occupying another vessel or actual subsumption requires the existing real extraction/consent path. Accompaniment is not kidnapping custody.

Source: Book PDF 182; delegated recommendation.

Reason: The printed offer gives the affected Girl her own reply. Travelling in her currently piloted own Frame preserves her existing embodiment; nothing permits commandeering another person's vessel or bypassing extraction.

Alternatives: Force every accepting Girl to abandon her Frame; Move somebody else's occupied Frame without authority.

Implementation/adjustment: The actual owned reply controls the outcome and does not spend, heal or inherit resources. The actual owned reply controls the outcome and does not spend, heal or inherit resources. Review pending source work before revision; preserve original receipts and immutable history.

### `harpy-killer-and-capture-facts`

Use the original damage source's actual opponent as killer where available. Otherwise the actual source adjudicator records the factual original killer. Shutdown/capture records an actual present Foundation captor, preserves unknowns and existing custody/consent gates, and never spawns a proxy NPC or fabricates transport.

Source: Book PDF 182; delegated recommendation.

Reason: Consequences refer to the actual original killer or captor. A replacement character, willingness to surrender, or a missing fictional person cannot establish historical identity or physical custody.

Alternatives: Treat the chooser's current replacement as killer; Turn willingness to surrender into invented physical access.

Implementation/adjustment: The death Tag and custody remain bound to actual original ActorRefs. The death Tag and custody remain bound to actual original ActorRefs. Review pending source work before revision; preserve original receipts and immutable history.

### `harpy-cut-link-continues-fight`

Severing the link completes the Defeat roll and its damage-source work while preserving a standing exact-original requirement to fight until actual typed Helplessness. This lets genuine combat continue after chat restoration; acknowledgement cannot satisfy it, and voluntary escape/navigation remains blocked while required.

Source: Book PDF 182; delegated recommendation.

Reason: The printed obligation requires later combat, which cannot occur if the completed Defeat retains the same chat lock indefinitely. A durable exact-original effect preserves the obligation without inventing Helplessness.

Alternatives: Hold the roll's chat lock forever while requiring later combat; Mark the Harpy Helpless automatically.

Implementation/adjustment: Uses a durable source effect and an actual-condition finish operation. Original ending before Helpless needs the source-ended closure integration listed below. Uses a durable source effect and an actual-condition finish operation. Original ending before Helpless needs the source-ended closure integration listed below. Review pending source work before revision; preserve original receipts and immutable history.

### `rift-closure-original-owner`

The lasting Rift remains open until its original Harpy controller explicitly closes that source effect; closure does not return, heal or move bodies already offstage. The source-owned closure procedure does not grant a successor any fictional authority.

Source: Book PDF 182; delegated recommendation.

Reason: A lasting Rift has its own printed owned closure choice. Keeping that original effect procedure distinct from a new body action prevents timers, staff acknowledgement, and replacements from choosing for its owner.

Alternatives: Automatically close on a timer or body death; Leave a lasting effect without its printed owner control.

Implementation/adjustment: An owned lasting-effect procedure remains distinct from creating a new body action. An owned lasting-effect procedure remains distinct from creating a new body action. Review pending source work before revision; preserve original receipts and immutable history.

### `ended-director-owned-procedure`

A real original human may finish an already-owned source procedural question after the actual Director body ends. Require immutable original cast/Director-death/episode proof. No new fictional body effects, unrelated questions or global GM authority are granted. A required Battle GM Play uses its frozen human scene-judge principal separately from the actual campaign appointment.

Source: Book PDF 15, 116, 117, 118, 192; delegated recommendation.

Reason: Fictional body death does not erase an already-assigned human procedure. Actual immutable episode/death proof preserves only that finite source scope; global GM authority and a dead NPC's body effects do not follow.

Alternatives: Transfer the pending ruling to an unrelated human or new body; Deadlock the already-owned procedural question.

Implementation/adjustment: Source-scoped OOC Tags carry an authenticated finite HandlerPlay grant, the actual campaign appointment, and actual creation event; retained same-person Tags preserve this source. Source-scoped OOC Tags carry an authenticated finite HandlerPlay grant, the actual campaign appointment, and actual creation event; retained same-person Tags preserve this source. Review pending source work before revision; preserve original receipts and immutable history.


## Current bounded gameplay clarification checkpoint

These delegated recommendations preserve pending independent source review and human acceptance. They change no release gate or enabled module. Exact implementation scope and evidence are in the M3 acceptance report.

### `harpy-optional-extra-maneuver-timing`

The Harpy may take one additional distinct Engage option at any Engage or All Out Assault tier. In Assault it is selected before primary consequences, uses an actual owned usable Asset, adds no separate roll and does not introduce Engage tier damage.

Source: Rulebook PDF25/printed23; PDF181/printed179; delegated recommendation.

Reason: The adjustment says may and for either Play without limiting result tiers. Keeping each Play's own consequence table avoids inventing a second result.

Alternatives: Only permit the extra at successful tiers; Resolve a second Engage roll or add its damage to Assault

Implementation/adjustment: Optional owned native response precedes the actual Assault result; no primary consequences are waived. Requires printed-rule clarity review. Changes exact maneuver count/timing for pending Harpy actions; preserve original source receipts and resolve pending choices before changing.

### `engage-conversation-circumstances`

Engage records each selected maneuver, real actor/opponent/Asset, actual human-authored resulting circumstances and immutable source event. It does not assign an unchosen map cell or invent numeric armour/damage.

Source: Rulebook PDF25/printed23, eight Engage options; delegated recommendation.

Reason: The printed options describe battlefield position and circumstances in the Conversation rather than a coordinate or HP procedure.

Alternatives: Automatically choose a grid destination; Treat a mere handled acknowledgment as a maneuver effect

Implementation/adjustment: Typed canonical Maneuver facts retain exact effects for source review and subsequent Conversation judgments. Actual Asset damage still uses the sole damage/Defeat port. Requires printed-rule clarity review. Any future automated position consumer must require actual player-chosen source facts; preserve historical maneuver records.

### `handler-tag-original-human-choices`

Removing an observed actual Cadre Handler Tag is diceless and may occur during another held Play. Favour asks the original Handler without an automatic reward; Compel lets that original human choose pausing for control or acting on the Tag. Attention is recorded directly.

Source: Rulebook PDF11 / printed9, Handler Tags; delegated recommendation.

Reason: The printed alternatives specify direct attention, optional favours and two Handler responses. They do not grant dice, automatic resources or a new Handler Play.

Alternatives: Infer a favour grant or mechanical reward from the request; Automatically choose the Handler's action; Forbid all Tag uses while a scene is held

Implementation/adjustment: Actual source-bound requests and original-human native replies; attention produces an original-controller private Inbox notice with only a technical read receipt, no fictional answer or required mechanical work. Saved private receipts remain readable under unavailable rules; new gameplay remains strictly gated. Safety pause blocks mechanical mutations. Requires printed-rule clarity review. Preserve consumed Tag receipts and pending original-body ownership when revising.

### `handler-tag-consumption-during-proposals`

Spending a Handler Tag invalidates only uncommitted proposals that relied on it, returning those choices to their original humans without rerolling. An already committed modifier remains; a repeated-Tag decision for the now removed Tag closes without inventing an Identity or rejection action.

Source: Rulebook PDF11 / printed9: other-player Tag window and Handler Tag removal at any time; delegated recommendation.

Reason: Both source rules must coexist. A consumed Tag cannot remain newly selectable, but consumption does not refund or replace a modifier already committed by an actual earlier event.

Alternatives: Disallow removal while any Play is held; Keep an uncommitted removed Tag as an active resource; Undo a committed modifier or invent a required replacement Identity

Implementation/adjustment: Only exact actual Handler body and Tag IDs are matched; known receipts and unrelated human choices remain. Requires printed-rule clarity review. Pending Tag windows and repeated-Tag decisions need source-aware reconciliation before changing timing.

### `handler-tag-source-visibility-and-ending`

The private picker exposes only observed Handler Tags. The original Girl supplies the factual request. If the exact original Handler role subsequently ends, its former human may close only that request against a proved original ending; a successor gains no obligation or fictional action.

Source: Rulebook PDF11 / printed9; existing original-person lifecycle rules; delegated recommendation.

Reason: A private selector must not reveal unobserved content or transfer an old request through a human account to a new character.

Alternatives: Show every private Tag to any account; Let a successor answer as the old Handler; Leave the original request impossible to resolve after a proved ending

Implementation/adjustment: Original ActorRefs, immutable source history and actual ending proof are required. This does not add M4 fictional-knowledge automation. Requires printed-rule clarity review. A different visibility or post-ending policy needs migration of pending source requests; retain immutable consumed Tag records.

### `director-handler-tag-actual-target`

A real Director uses Handler Tag rules on that Director's own world Tag record and controlled body. This never spends the Cadre Handler's Tags or lets the OOC GM answer for the Director. Temporary Girl roll rules do not transfer the original Cadre Handler's Tag ownership to the Director.

Source: Rulebook PDF11/printed9 and PDF192/printed190; delegated recommendation.

Reason: The Director explicitly uses Handler rules. Actual target/controller references keep this distinct from the Cadre Handler and its temporary rules context.

Alternatives: Allow Tag use only on the Cadre Handler; Treat every NPC Handler job as a Director; Use the campaign GM account as every Director's controller

Implementation/adjustment: Known present Director selector uses its sole world Tag authority; original controller owns any reply. A favour agreement gives no automatic help or free mechanical benefit; actual Director help still needs its separate price system. Requires printed-rule clarity review. Preserve exact NPC IDs and source-human audience; never reassign pending requests to successor Directors.

### `mandatory-forbidden-dormant-dive`

An actual Dormant-required Dive forbidden by completed original surgery uses existing source-specific honest manual adjudication. Original appointed or selected scene judge human assigns whole integer pre-Tag total with reason; no RNG/faces/Heat/Identity spend, then normal actual Tag and outcome owners. Inherited prohibition remains after actual rebirth.

Source: official private rulebook PDF24 / printed22; official private rulebook PDF165 / printed163; official private rulebook PDF196 / printed194; delegated recommendation.

Reason: The required Dormant Dive and a completed surgery prohibition can both apply, but the book supplies no exception for the resulting compulsory impossible roll. An owned explicit no-roll decision resolves that conflict without inventing ability restoration or dice.

Alternatives: Deadlock the compulsory source permanently; Invent ability restoration or an automatic favorable result

Implementation/adjustment: Required(dormant_dive_work) authenticates original body/controller, exact work revision, original surgery and source judge; AdjudicationService writes honest faces:null receipt then normal owned Tag/Dive pipeline. Only actual pending Dormant source work and exact original actor/controller; voluntary forbidden Dive remains unavailable.

### `harpy-off-duty-roll`

Retain one real 2d6 roll with base modifier zero because Harpies have no ranked Status; no Heat/Identity gain or spending. All tiers use the printed Harpy hide and recovery replacement, followed by actual owner choices and factual navigation review.

Source: official private rulebook PDF181 / printed179; delegated recommendation.

Reason: Harpy Off-Duty explicitly replaces scenes, whereas the adjacent Sensor exception explicitly replaces rolling. Harpies have no Cadre Status value, leaving the ordinary roll modifier undefined; retaining dice with zero base is a delegated interpretation.

Alternatives: Treat all Harpy Off-Duty as diceless; Invent a current PC Status modifier

Implementation/adjustment: Actual ActorPlay uses one 2d6/base0/noHeat receipt and normal Tags; HarpyRest owns hide facts, original judge review, all-tier recovery and actual reviewed return independently of Cadre Period. No Cadre Period, Status, Permission, mission/reward or same-human sheet mutation.

### `harpy-off-duty-identities`

Owner may author any number of ordinary Identities, preserving actual protected retained Identities. Existing matching names retain stable IDs; new names get new IDs; explicit owner hide/adjustment confirmation clears marks. Transport/UI payload bounds do not become fictional four-Identity cap.

Source: official private rulebook PDF179 / printed177; official private rulebook PDF181 / printed179; delegated recommendation.

Reason: The Harpy rebirth text allows any number of new Identities and the Harpy Off-Duty text allows adjustment freely, while core Girl rules set a four-Identity cap. Applying the Harpy exception avoids silently deleting actual retained larger lists.

Alternatives: Import basic Girl four-Identity cap; Retain current count only

Implementation/adjustment: Source owner explicitly supplies ordinary names and confirms adjustment; protected retained IDs remain, matching names retain actual IDs and chosen marks clear. Existing Embrace threshold interaction remains identified for source clarity rather than automatic truncation. Existing basic Embrace rule still replaces exactly one ordinary Identity at its printed threshold; never shrink an already larger Harpy list. Review existing len(all identities)>=4 threshold versus actual Free additional Identity as a distinct clarity item.

### `owned-director-procedures-after-death`

The original human selected as scene Director may finish only already-owned procedural Tag/Dive/hide questions from the frozen original episode after actual Director death. Exact original cast/history/receipt and real ending proof required; living roles retain their own actual resources, otherwise original human marker is finite OOC plus/minus one without body/Bond authority.

Source: official private rulebook PDF5 / printed3; official private rulebook PDF24 / printed22; official private rulebook PDF192 / printed190; delegated recommendation.

Reason: Actual Director death changes future role authority but does not identify a new author for a human-owned question already created by a committed original episode. The book does not define pending-question reassignment.

Alternatives: Transfer every pending answer to current campaign GM; Deadlock all already-owned questions

Implementation/adjustment: owned_director_procedure proves immutable original episode/cast/receipt, actual Director death and current same Harpy vessel; actual humans finish only finite owned procedures. Marker fallback is OOC plus/minus1/Bond0 and never a dead NPC body. No dead NPC mutation/revival, no new scene-role/global GM privilege. New episodes use actual current adjudicator.

### `harpy-cut-link-original-ending`

An exact original Harpy death closes her standing cut-link fight as original_died with actual ending event; it does not claim Helpless, healing, movement or successor compliance. Proposed original-owned hides/routes end sourcefully; existing offstage body/corpse position stays unknown.

Source: official private rulebook PDF182 / printed180; delegated recommendation.

Reason: A cut-link result requires fighting until Helpless; actual death makes that future body action impossible and is not itself the printed Helpless condition. Source closure must distinguish the two instead of forging compliance.

Alternatives: Invent Helpless to satisfy fight condition; Keep an impossible dead-body fight pending forever

Implementation/adjustment: Authoritative Harpy die records ended_event/original_died on exact standing fight; proposed hides/routes end with actual source, active offstage corpse location stays unknown. Actual already-damaged Girl Assets on unlink instead cause true source-foe Helpless. Only impossible exact-original Off-Duty source choices close without human response; true final-act/death-Tag procedures remain owned.

### `postcareer-harpy-killer-tag`

If factual killer is already an immutable ended original, record the chosen death Tag with stable ID and exact original recipient/giver in actual Harpy Defeat effect, leaving original archive snapshot immutable and replacement untouched. On a genuine same-original return, prove that actual recorded effect and materialize once with same stable ID.

Source: official private rulebook PDF182 / printed180; delegated recommendation.

Reason: The final Tag is inflicted on the actual killer, while a same-account replacement is a different character. Rewriting an immutable archive would falsify the earlier snapshot, and assigning to the successor would change the printed recipient.

Alternatives: Grant Tag to current same-UID successor; Rewrite original archived sheet; Discard the printed final Tag

Implementation/adjustment: DefeatEffect is sole postcareer consequence with exact original recipient/giver and stable TagID; ended_actor_source proves real original ending. Actual original-return hook verifies immutable effect and materializes once; archive/new-body snapshots remain unchanged. Actual archived Handler no-inheritance and ordinary genuine-return regressions are covered; a full combined postcareer-Tag original-return scene is not separately exercised in current fixture. No extra live Tag pool; same-person late rebirth recipient handling remains separate and requires actual birth proof, never UID fallback.

### `handler-void-performed-self-cut`

Knife removal records the actual patient-authored cut, body site and persistent wound with actual source event; it does not invent numeric Asset damage or another Handler Asset-replacement trigger.

Source: official private rulebook PDF19 / printed17; delegated recommendation.

Reason: The knife option describes actual removal but supplies no numerical damage cost or extra Handler Asset trigger. Inventing one could recurse into unrelated death/Asset replacement choices.

Alternatives: Fabricate a numeric Handler Asset injury; Treat choosing the label as removal without actual performed account

Implementation/adjustment: HandlerVoid stores performed wound, localized site and removal event under actual patient audit; no Asset damage/HP, Pilot resources or movement changes. Only actual source body/controller; no Pilot resources, transport or unrelated healing.

### `handler-void-drugs-immediate-vs-treatment`

Actual localized experimental-drug manifestation and halted spread satisfy the immediate printed choice while retaining void_present and an owned source treatment task. Subsequent actual removal remains necessary; no automatic execution or fictional timer is invented.

Source: official private rulebook PDF19 / printed17; official private rulebook PDF20 / printed18; delegated recommendation.

Reason: The printed drugs option halts spread; the subsequent note separately requires corruption removal or institutional consequences. The book gives no timer or automatic institution response, so immediate choice completion and persistent treatment must remain distinct.

Alternatives: Pretend drugs removed all corruption; Hold unrelated completed interaction forever pending later surgery; Automatically execute the Handler

Implementation/adjustment: Drugs creates real localized manifestation/spread_halted with void_present; source immediate work completes only after authenticated actual choice. Separate owned treatment remains visible even after source work resolves, with real later removal or actual original death. Original source parent may proceed after actual stabilization; actual biological condition remains pending on same original body until real removal or death.

### `handler-void-performed-surgery`

Choosing surgery requests actual immediate treatment; completion requires actual original human factual attestation that personnel performed the procedure and removed corruption, with specific account. It grants no other healing, coordinates, transport or NPC dialogue.

Source: official private rulebook PDF19 / printed17; delegated recommendation.

Reason: Requesting personnel and recording that surgery occurred are different facts. No automatic destination, surgeon controller or dialogue is supplied, and the text does not grant unrelated healing.

Alternatives: Auto-teleport to a medical bay and manufacture a surgeon response; Treat request alone as performed removal

Implementation/adjustment: Surgery choice leaves Void present and original source held; actual original human later attests performed procedure and removal with account. Completion proves the actual surgical event; physical coordinates/resources are untouched. Source remains held until actual performed-procedure source, and no fake consent or fake human reply is emitted.

### `handler-director-void-rule-precedence`

Actual Director NPC uses normal Handler physiology with its own original body/controller, independently of main Handler. Main Handler in an actual Director Girl-rules context uses actual Girl Asset corruption, never the normal Handler option list.

Source: official private rulebook PDF19 / printed17; official private rulebook PDF192 / printed190; delegated recommendation.

Reason: PDF192 explicitly assigns Handler rules to the actual Director and Girl rules to the Handler in that presence. An ActorRef kind or human GM account cannot override that printed rule context.

Alternatives: Apply normal Handler physiology to every Handler ActorRef; Impersonate the main GM body when Director NPC gains Void

Implementation/adjustment: Normal Handler and actual Director NPC use original-body HandlerVoid; actual Handler Girl context uses distinct HandlerGirlVoid and sole real Item Assets. Controller, body and rule context remain separate and source-proved. No Kind/UID coercion or copied Pilot/Frame resources.

### `handler-girl-existing-asset-factual-registration`

Zero modeled mechanical Girl Assets require an actual owner proposal of real preexisting gear/cybernetics/capability plus original source GM/selected judge factual review. Preserve actual damage and weapon facts, cap at four, store one sole HeldItem Asset authority with immutable proposal/review proofs. No automatic baseline two, new gear, paid Ability, repair or Frame is granted.

Source: official private rulebook PDF15 / printed13; official private rulebook PDF19 / printed17; official private rulebook PDF192 / printed190; delegated recommendation.

Reason: The Director rule grants zero Heat and two Identities but does not assign a Frame or mechanical starting Assets. Girl Void requires an actual uncorrupted Asset; zero unknown Assets cannot be treated as an all-Void set or a license to invent two defaults.

Alternatives: Invent two starting Assets; Treat zero Assets as all Void; Use normal Handler physiology despite Girl-rule context

Implementation/adjustment: Original patient proposes real existing capability/gear, frozen source judge factually reviews, cap4 is rechecked and actual existing damage/weapon status is preserved. HeldItem is sole mechanical authority; immutable proposal/review/origin proof is checked by Item.prove_item. Failed facts leave forced source pending, not cancelled. If no eligible facts can be established, actual factual review stays pending. Rejecting an unproved proposal does not veto the forced Void consequence.

### `handler-girl-void-choice-ownership`

For Mockingbird high source, original caster chooses the actual existing counterpart Asset; affected Handler Girl writes its Void change. Factual registration owner/judge roles remain separate.

Source: official private rulebook PDF19 / printed17; official private rulebook PDF36 / printed34; official private rulebook PDF192 / printed190; delegated recommendation.

Reason: Mockingbird high explicitly gives the caster the Asset choice, while the general Void rule describes the affected person rewriting the change. Factual setup must not transfer the caster choice to patient or bot.

Alternatives: Allow patient or bot to substitute for original caster target choice

Implementation/adjustment: After actual owner/judge fact setup, frozen original caster selects eligible AssetID, then affected original patient supplies Void description. Completion proves both actual audited steps and actual sole Item mutation, with rollback for label-only completion. Source audit proves original caster selection, actual patient rewrite and actual sole Item mutation before completing held work.

### `handler-girl-allure-without-assigned-frame`

A nonempty all-Voided actual Girl Asset set records persistent source-bound allure. Handler Girl has no granted assigned Frame; occupying a foreign Frame cannot cause invented fusion, acquisition or transformation.

Source: official private rulebook PDF19 / printed17; official private rulebook PDF192 / printed190; delegated recommendation.

Reason: General Girl allure is conditioned on entry into your Frame, but the temporary Handler Girl context provides no assigned Frame. Inferring one from a foreign occupied vessel would grant resources and a transformation not established by source.

Alternatives: Create an assigned Frame from an occupied foreign vessel; Convert immediately without actual own Frame entry

Implementation/adjustment: A nonempty all-Voided actual Girl Asset set records original-body allure/assigned_frame=None. Asset consequence and original parent complete; no Frame/Harpy/Pilot or transport is created. Any future real assignment requires a separate proved continuation. Actual Asset rewrite and original interaction complete while typed original-body allure remains, with no Frame/Harpy/Pilot fabrication.

### `handler-girl-already-void-source-coalescence`

An additional actual forced Void source on a NONEMPTY already all-Voided Girl Asset set coalesces its true allure condition without a fabricated Asset choice, rewrite or acknowledgment. Source proof and real actual high response must precede automatic callback.

Source: official private rulebook PDF19 / printed17; official private rulebook PDF36 / printed34; official private rulebook PDF192 / printed190; delegated recommendation.

Reason: Once a nonempty actual Girl Asset set is already all Void, a further forced gain has no new uncorrupted Asset to choose. The actual allure condition remains true, but an extra choice or acknowledgment would be fabricated.

Alternatives: Treat empty unknown Assets as all Void; Ask for a fictitious already-corrupted target mutation; Deadlock a proven source with no eligible new Asset

Implementation/adjustment: Real accepted trigger/high receipt/actual response precede post-response source synchronization, which proves nonempty actual all-Void Item Assets and automatically completes exact source. Empty or unknown sets remain factual-review work; no duplicate mutation or fake human reply. No additional resource mutation or RNG; each actual source is traced; no fake human answer.

### `owned-handler-girl-void-after-director-death`

Actual already-committed Girl-rule Void source preserves its original body/context and original human factual judge after Director death. Only that prior owned procedural review and patient/caster choices may finish; Director NPC remains dead and no new Girl role/global GM authority is granted.

Source: official private rulebook PDF19 / printed17; official private rulebook PDF36 / printed34; official private rulebook PDF192 / printed190; delegated recommendation.

Reason: A committed original Girl-rule corruption effect remains causally owed even if the Director later dies and future Handler rules change. The source does not reassign that pending human factual review or undo the original physical effect.

Alternatives: Silently switch to normal Handler physiology; Transfer all original questions to a new principal; Deadlock a real already-committed source

Implementation/adjustment: Frozen original context/body/caster/judge proof allows only prior owned factual review and original patient/caster steps. Original human reviewer may act OOC after NPC death, with no NPC revival or new role authority; actual Handler body death closes only its impossible source without rewrite/removal/Frame fabrication. Same physical body proofs and immutable source epoch required; actual Handler body death closes only its impossible source work without fake rewrite/removal or successor inheritance.

### `offstage-world-advance-preserves-absence`

Advance the actual on-map eligible Gorgons once; a source-proved offstage body or Directed goal has no invented map action. Preserve its cached canonical World coordinates only as historical storage, mask them in all current physical views.

Source: Rulebook PDF 123, 166, 182 / printed 121, 164, 180; delegated recommendation.

Reason: The printed map operations require actual presence; a Rift crossing does not magically return someone for an end-of-period step.

Alternatives: Block the entire period until every actor physically returns; silently move cached offstage coordinates.

Implementation/adjustment: Implemented only within this bounded source workflow; source eligibility, original human choices, release gates and immutable history remain. Requires printed-rule clarity review. Periods may continue while the absent actual actors retain source-bound offstage obligations; no rewards, travel or relocation is invented.

### `last-base-aftermath-timing`

Apply concrete destruction and real Budget trigger before the originating strike completes. Preserve actual required job-loss/aftermath work that blocks mission/period progression, without holding the strike chat through transport, rescue or replacement character setup.

Source: Rulebook PDF 25, 122, 150 / printed 23, 120, 148; delegated recommendation.

Reason: Printed immediate collateral and longer institutional consequences occur at different fictional times.

Alternatives: Keep strike channel locked until all employment/transport/new persona steps finish; acknowledge the aftermath without actual effects.

Implementation/adjustment: Implemented only within this bounded source workflow; source eligibility, original human choices, release gates and immutable history remain. Requires printed-rule clarity review. Actual mission/OffDuty remains blocked until the real source episode completes; unrelated strike chat can restore safely.

### `last-base-institutional-outcome`

The frozen original human judge makes the source employment review, including retained-under-review because the book says likely, or actual living fired/prison outcomes. New Handler requires genuine creation/acceptance; execution requires separate real Foundation agent acceptance and actual performance; reassignment requires each original owner transport facts and a real new map.

Source: Rulebook PDF 122 / printed 120; delegated recommendation.

Reason: Likely is not automatic death; firing and imprisonment do not erase or replace the original body.

Alternatives: Automatically kill the Handler; auto-spawn a replacement; teleport all actors onto a new map; manufacture an executor reply.

Implementation/adjustment: Implemented only within this bounded source workflow; source eligibility, original human choices, release gates and immutable history remain. Requires printed-rule clarity review. Historical original bodies/resources/custody and old map are privately preserved. Known contradictory access/custody blocks execution or transport. The institutional judge remains an OOC source role if its prior fiction body ended.

### `sprite-finite-physical-interception`

Offer living known co-located actual Sprites one source opportunity per human controller before an incoming physical Asset/destroying/fatal blow, excluding Engage and deliberate self-cost. First real interception damages the chosen intact Sprite Asset and shields the original body, including fatal Core strikes; original roll, modifiers and target remain frozen.

Source: Rulebook PDF 15, 26, 162, 166 / printed 13, 24, 160, 164; delegated recommendation.

Reason: Leap in to take a blow names a physical interception, not a new Core strike against an unexposed Sprite or a new RNG decision.

Alternatives: Retarget the original receipt/Asset modifier; automatically expose/kill the Sprite Core; allow self-cost escape; forge every nonresponding controller pass.

Implementation/adjustment: Implemented only within this bounded source workflow; source eligibility, original human choices, release gates and immutable history remain. Requires printed-rule clarity review. An actual explicit decline applies the original source consequence. Multiple actual Sprites per human share an ID dropdown. Other opportunities are source-superseded without fake human responses.

### `gorgon-damaged-asset-capability`

A Gorgon may declare a real damaged owned Asset only after actual frozen judge confirms its described capability before any effect. It remains damaged; arbitrary gear or body description is not a mechanical Asset.

Source: Rulebook PDF 15, 162 / printed 13, 160; delegated recommendation.

Reason: The Gorgon Play requires stating its actual Assets; damaged-vs-functional fighting is a Conversation fact rather than invented repair.

Alternatives: Ban all damaged Assets categorically; silently treat the damaged Asset as repaired; admit any untracked gear as an Asset.

Implementation/adjustment: Implemented only within this bounded source workflow; source eligibility, original human choices, release gates and immutable history remain. Requires printed-rule clarity review. Source intent, resource hash, current ownership, judge account and approval remain auditable. Denial performs no effect.

### `vacant-current-frame-snoop-loss`

Out-of-battle Snoop damage to an exactly proved vacant current Frame changes its actual Asset only. Losing its final intact Frame Asset disables that actual Frame; it does not teleport or roll Defeat for an absent Girl. Real repair is required before later piloting. Independent Core or other actual occupant is gated to its own source port.

Source: Rulebook PDF 15, 29 / printed 13, 27; delegated recommendation.

Reason: Defeat says defeated in battle; the note assumes a present Pilot in a Frame. Vacancy is a separate actual physical source fact.

Alternatives: Roll Defeat for the remotely absent owner; silently place the owner inside; damage a replacement/parked Frame alias.

Implementation/adjustment: Implemented only within this bounded source workflow; source eligibility, original human choices, release gates and immutable history remain. Requires printed-rule clarity review. Original Girl body/vessel/position/custody/resources remain untouched. Exact current Frame instance and real discovery/relevance/reach are mandatory.

### `gorgon-attack-target-owned-asset`

When an attacked Girl accepts Asset damage instead of a response Play, her actual controller selects her currently intact physically available Asset. Source counter/response ownership never transfers to the attacking Gorgon human.

Source: Rulebook PDF 162 / printed 160; delegated recommendation.

Reason: The Girl must make a Play or it will damage an Asset, while the source does not explicitly name who selects the slot; owner choice preserves actual resource agency.

Alternatives: Attacking Gorgon controller chooses all victim Assets; actual judge chooses every slot.

Implementation/adjustment: Implemented only within this bounded source workflow; source eligibility, original human choices, release gates and immutable history remain. Requires printed-rule clarity review. Only the slot-choice default changes; the mandatory incoming blow, real last-family consequences, and optional Sprite opportunity remain source-owned.

### `gorgon-contest-real-asset-destruction`

Judge selects the actual losing Asset among the actual pitted Assets. Remove that exact active resource and preserve immutable destroyed provenance; a real Harpy final Frame loss creates actual HarpyDefeat. Directed protection still requires real judge-confirmed indirect approach.

Source: Rulebook PDF 162, 164 / printed 160, 162; delegated recommendation.

Reason: The book says destroying the losing Asset, not merely marking damage on a resource that can be freely repaired.

Alternatives: Use ordinary damage; remove an unrelated resource; infer fictional Core death or fake numerical HP.

Implementation/adjustment: Implemented only within this bounded source workflow; source eligibility, original human choices, release gates and immutable history remain. Requires printed-rule clarity review. Current sole-origin base/HeldItem resource is removed once; actual wreckage/original JSON/source event remains private and cannot be repaired back into a duplicate pool.

### `city-threat-two-successful-collateral-plays`

Count each distinct actual Collateral Damage Play once if any of its real selected effects applies. Wholly interrupted, unreachable, or capability-denied Plays add no success. On the actual second success at the threatened City, destroy that same City through the ordinary sole collateral/Budget/territory source port.

Source: Rulebook PDF 144, 162 / printed 142, 160; delegated recommendation.

Reason: The source says successfully uses Collateral Damage twice, rather than requiring the structure option or counting each chosen option as a separate Play.

Alternatives: Count only successful structure destruction options; Count each chosen effect separately; Count interrupted or retried Plays

Implementation/adjustment: Implemented only within this bounded source workflow; source eligibility, original human choices, release gates and immutable history remain. Requires printed-rule clarity review. Source-bound once-only counters; real City destruction and many-residents casualty population fact, while individual NPC fates remain unconfirmed unless actually selected/proved caught. Actual absent/dead source Gorgon does not gain map effects from a cached cell.

### `directed-ended-person-goal-deferral`

If its actual NPC goal is canonically dead, defer only that Directed Gorgon with reason actual_goal_ended and the exact original dead-body snapshot. Preserve corpse position and the existing goal; other present Gorgons advance normally.

Source: Rulebook PDF 123, 166 / printed 121, 164; delegated recommendation.

Reason: The body has ended. Requiring its resurrection or advancing from an unrelated replacement would invent physical facts. The printed rule supplies no automatic new person/goal after the target dies.

Alternatives: Block the entire period; Treat the goal automatically fulfilled; Retarget a same-human successor; Automatically chase the corpse as a living person

Implementation/adjustment: Implemented only within this bounded source workflow; source eligibility, original human choices, release gates and immutable history remain. Requires printed-rule clarity review. No automatic goal replacement, fulfillment, movement, resurrection, rewards or corpse transport. Actual later goal decisions remain explicit source actions.

### `mockingbird-risk-order`

After actual Tags and any source-owned finite roll adjustments, the original owner may pay real Void to choose 8,9,10. Preserve raw receipt; finish original primary effect choices before resolving genuine Void continuation.

Source: Rulebook PDF 35, 24 / printed 33, 22; delegated recommendation.

Reason: Risk replaces the actual final pre-consequence total. Preserving original Tags, primary effects and one raw receipt avoids inventing a reroll or applying original effects to a successor.

Alternatives: Resolve transformation before original effects or adjust before Tags.

Implementation/adjustment: Implemented only within this bounded source workflow; source eligibility, original human choices, release gates and immutable history remain. Requires printed-rule clarity review. No wrongbody primary effects; no duplicate RNG/Heat; exact source roll preserved.

### `mockingbird-risk-existing-resistance`

A Risk cost while already resisting the same original current threshold is covered by that actual threshold; do not create another Keep or circular child continuation.

Source: Rulebook PDF 35 / printed 33; delegated recommendation.

Reason: The cost contributes to the same actual current all-Void threshold. A second circular resistance would not describe a distinct body or threshold.

Alternatives: Create an independent resistance for every voluntary cost.

Implementation/adjustment: Implemented only within this bounded source workflow; source eligibility, original human choices, release gates and immutable history remain. Requires printed-rule clarity review. One real source resistance resolves actual ongoing threshold, cost still paid.

### `mockingbird-risk-off-duty-boundary`

Synchronize the final shifted OffDuty/Observation roll once to its original period before actual Risk consequence; future independent scenes/recovery retain originalCID and actual ending semantics and do not hold roll chat indefinitely.

Source: Rulebook PDF 35, 25, 26 / printed 33, 23, 24; delegated recommendation.

Reason: The original roll qualifies the real period before future scenes. Holding its chat lock over the whole period prevents actual required scenes and risks successor benefit inheritance.

Alternatives: Keep all future period scenes/recovery under original roll lock or transform before saving actual final period result.

Implementation/adjustment: Implemented only within this bounded source workflow; source eligibility, original human choices, release gates and immutable history remain. Requires printed-rule clarity review. No globalpending deadlock, no period roll resync or successor benefit inheritance.

### `mockingbird-immunity-only-harpy`

Risk suppresses Girl allure/Harpy outside the stated own-Frame criterion, but preserves the assigned fully-Voided Frame consequence; actual outside body uses abandoned Frame/Gorgon source, unknown pose gets actual physical review.

Source: Rulebook PDF 19, 35 / printed 17, 33; delegated recommendation.

Reason: The printed immunity is specifically to becoming a Harpy under the named condition; it does not waive the separate actual fully corrupted Frame consequence.

Alternatives: Existing broad no-followup branch outside Frame also waived Frame growth.

Implementation/adjustment: Implemented only within this bounded source workflow; source eligibility, original human choices, release gates and immutable history remain. Requires printed-rule clarity review. No invented immunity, no movement into cockpit or copied body, original Girl stays outside while real Frame can become Gorgon.

### `call-classification-caps-and-intrinsic`

Batch real family changes obey final4Girl/5Frame caps and explicit excess non-Void ordinary replacements; preserve original intrinsic ID/marker/sourceclassification. Additional privilege applies only actual current Frame intrinsic in Frame family.

Source: Rulebook PDF 15, 35 / printed 13, 33; delegated recommendation.

Reason: Moving existing Assets changes their actual family without erasing their origin or waiving the ordinary family caps. A former Frame intrinsic is not a permanent transferable free slot.

Alternatives: Waive caps for any-number wording, discard intrinsic history or keep oldFrame privileged forever.

Implementation/adjustment: Implemented only within this bounded source workflow; source eligibility, original human choices, release gates and immutable history remain. Requires printed-rule clarity review. No automatic overflow deletion/freeAsset/copy; movedGirl countsGirl, movedback oldFrame intrinsic counts ordinary after replacement.

### `npc-beyond-intense-real-heat-only`

Preserve actual Intense Bonds with ordinary NPCs; deepening beyond Intense grants +2 only to each actual Heat-bearing participant. Ordinary NPCs gain no invented Heat resource.

Source: Rulebook PDF 14, 36 / printed 12, 34; delegated recommendation.

Reason: The printed Bond rule can coexist with NPC Bonds even though ordinary NPCs have no Heat resource; preserving the edge and applying existing real resources avoids excluding printed social relations.

Alternatives: Disallow further deepening Intense NPC Bonds, or invent NPC Heat.

Implementation/adjustment: Implemented only within this bounded source workflow; source eligibility, original human choices, release gates and immutable history remain. Requires printed-rule clarity review. Snoop, intimacy and source-supported social Punishments may deepen valid NPC Bonds; current Pilot/Handler/Harpy counterpart gains actual +2 Heat, no proxy sheet or new NPC runtime. External actors with unimplemented resource ports remain gated.

### `starry-current-tag-capability-lifetime`

Preserve the immutable printed Person choices separately; derive Starry capability extras only while its exact original Tag remains present on the actual source holder. Marking alone keeps the Tag; actual removal stops the extra. Same-person Harpy continuity requires real conversion proof and retained exact Tag ID.

Source: Rulebook PDF 35, 36 / printed 33, 34; delegated recommendation.

Reason: The printed duration depends on still having this Tag; storing its capability as a permanent native choice would outlive that condition.

Alternatives: Permanently merge the extra into the conversation snapshot, or end it merely on marking.

Implementation/adjustment: Implemented only within this bounded source workflow; source eligibility, original human choices, release gates and immutable history remain. Requires printed-rule clarity review. No permanent free capability, no successor UID inheritance, no rewrite of original roll/Tag consequence.

### `enforcer-master-known-total-order`

Master's Dog settles its finite optional +2, -2 or decline after actual Tags, before Risk chooses final8/9/10 and before all final ordinary Off-Duty benefit qualifications.

Source: Book PDF79 / printed77; interaction with Risk PDF35 / printed33; delegated recommendation.

Reason: Both mechanics change the known roll. A single ordered pipeline preserves actual raw receipts and prevents a benefit qualifying on an intermediate total.

Alternatives: Settle Risk before Master; qualify benefits on intermediate totals.

Implementation/adjustment: Current Enforcer candidate; independent source review and actual owner testing remain pending. No typed Rulings configuration field is implied by this documentation label. A future ordering change affects pending known receipts; retain source modifiers and do not reroll.

### `enforcer-master-actual-handler`

Master's Dog initial Bond and sleeping-room entitlement bind the actual fictional Handler body at acquisition, while Director scene adjudication is separate.

Source: Book PDF79 / printed77; delegated recommendation.

Reason: The benefit names your Handler; a selected Director source role does not become a replacement body or transfer an earned Bond. The room is fictional entitlement only, with no Discord staff access, human attendance, teleport or extra qualifying scene.

Alternatives: Transfer room and Bond automatically to every temporary Director or successor Handler.

Implementation/adjustment: Current Enforcer candidate; independent source review and actual owner testing remain pending. No typed Rulings configuration field is implied by this documentation label. Actual source relationship changes require source-backed adjustments; no silent transfer.

### `enforcer-pavlov-owned-obedience`

The original owner records actually following an order before Keep; optional good-soldier and bliss positives add to the normal tier results. A formal bot-issued numeric order is not required by the printed trigger.

Source: Book PDF79 / printed77; delegated recommendation.

Reason: The trigger is fictional obedience, not a software order-ID requirement. Its extra positives do not remove low negatives or alter ordinary Handler enough adjudication.

Alternatives: Require a numeric formal order; replace rather than add normal positives.

Implementation/adjustment: Current Enforcer candidate; independent source review and actual owner testing remain pending. No typed Rulings configuration field is implied by this documentation label. Changing trigger evidence affects future preparation; recorded prior own factual accounts stay history.

### `enforcer-firepower-effect-order`

The optional additional enemy Asset hit is selected, source-reviewed and applied inside the same actual Assault before its normal primary tier consequences are resolved; all actual follow-ups still block root completion.

Source: Book PDF79 / printed77; Assault PDF25 / printed23; delegated recommendation.

Reason: A high Assault can remove the original acting Frame through its own ordinary consequences. Applying its simultaneous earned extra hit first prevents that effect being stranded or reassigned to a successor body. No extra roll is granted.

Alternatives: Resolve all original high consequences first even if the source Frame is then lost.

Implementation/adjustment: Current Enforcer candidate; independent source review and actual owner testing remain pending. No typed Rulings configuration field is implied by this documentation label. Changing order requires preserving original known rolls, exact acting body and pending effect proofs.

### `enforcer-snoop-high-bond`

Snoop11+ asks one or two printed questions and trashes remaining relevant property, without implicitly also granting the8-10 Bond increase.

Source: Book PDF80 / printed78; delegated recommendation.

Reason: The high branch does not say as8-10 and omits the Bond clause, so effects follow their actual named tier.

Alternatives: Inherit the mid Bond increase on high.

Implementation/adjustment: Current Enforcer candidate; independent source review and actual owner testing remain pending. No typed Rulings configuration field is implied by this documentation label. If clarified otherwise, adjust actual source Bonds explicitly rather than rewriting completed rolls.

### `enforcer-snoop-absent-owner`

Snoop may concern an absent owner's actual accessible stored property. The original target controller supplies private printed findings; the OOC facilitator confirms existence/access for unmodeled ordinary props. This does not give an absent body scene knowledge or impose an OOC veto over fictional theft.

Source: Book PDF80 / printed78; physical source reconciliation; delegated recommendation.

Reason: The printed trigger concerns another person's stuff, not mandatory physical attendance by its owner. Canonical contradictory body/object positions still prohibit teleporting a carried item; ordinary descriptions create no mechanical Asset slots.

Alternatives: Require the owner physically present; invent objects from caster descriptions; require fictional target consent for theft.

Implementation/adjustment: Current Enforcer candidate; independent source review and actual owner testing remain pending. No typed Rulings configuration field is implied by this documentation label. Future location clarification affects pending source facts; actual object IDs/custody and private original answers remain immutable.

### `enforcer-explicit-source-rule-retention`

Frame Grafting may acquire actual reviewed Enforcer base rules for3; Ability Unlock2 remains Requisitions only. Paid Frame Swap may retain one actually owned supported base or acquired rule, with its original source and exact new Frame binding.

Source: Book PDF16 / printed14; Enforcer PDFs78–80 / printed76–78; delegated recommendation.

Reason: The book says rule for Grafting and Swap and Requisition for Unlock. A retained initial-effect rule does not re-run its acquisition effect. Native rule retention gets an actual paid Swap receipt; acquired rules keep their original grant and verified retention chain.

Alternatives: Allow only Personal Firearm retention; treat any Frame label as an unlock; grant all old Frame rules.

Implementation/adjustment: Bounded Enforcer candidate source workflow; real independent review and human player acceptance remain pending. Documentation key does not imply a new typed Rulings setting. Changing eligibility affects new selections and actual pending plans. Preserve completed paid swaps, original rule receipts, real physical objects and previously earned Bonds.

### `retained-enforcer-trigger-source-order`

A genuinely acquired or retained Enforcer Permission Trigger has a separate once-per-period review beside a different native trigger. Eligibility uses the actual pre-roll Off-Duty source, so later acquisition/restoration cannot qualify retroactively.

Source: Book PDFs16,78 / printed14,76; delegated recommendation.

Reason: Picking a rule preserves its actual consumer. Distinct genuinely owned triggers can each award their printed bonus; repeating one custody delivery for the same character and same trigger cannot award again. No new roll or synthetic delivery is granted.

Alternatives: Let a retained trigger stop working outside Enforcer; qualify a new rule against an old known roll; count one delivery repeatedly for the same trigger.

Implementation/adjustment: Bounded Enforcer candidate source workflow; real independent review and human player acceptance remain pending. Documentation key does not imply a new typed Rulings setting. Existing bonus and custody histories remain immutable. New rule ownership or delivery changes must use actual source events; never silently replay a completed award.

### `harpy-enforcer-low-status-capability`

An actual retained Enforcer Initiative uses the original Harpy actor/controller and real Frame contact. Its low Status-loss option is unavailable when that actual role has no Cadre Status resource; other source-supported printed low choices remain available.

Source: Book PDF79 / printed77; Harpy role resources PDFs177–181 / printed175–179; delegated recommendation.

Reason: A source does not create a missing Cadre Status track. Omitting the inapplicable option avoids pretending to lower a replacement Girl or converting an actual Harpy into a Pilot proxy. Original typed Tag, object custody, grasp and source-supported Punishment ports still operate.

Alternatives: Create a proxy Girl Status; apply disapproval with no mechanical Status loss; disable the whole retained Play.

Implementation/adjustment: Bounded Enforcer candidate source workflow; real independent review and human player acceptance remain pending. Documentation key does not imply a new typed Rulings setting. If Harpy Cadre membership is later explicitly supported, add a source-backed actual role resource before exposing the missing option. Do not rewrite original player characters or prior receipts.

## Focused workflow clarifications — 2026-11-05

Delegated recommendations below require printed-rule clarity review. They are recorded in `rules/registry.json` with rationale, alternatives and change impact. They do not enable production rules or certify M3.


### `budget-persistent-tag-nomination`

Source: Rulebook PDF152/printed150 Endgame5; PDF11/printed9.

The original Handler selects one actual original Cadre Girl; that Girl exclusively writes the Tag and account. Retain the exact source identities.

Rationale: Handler selects Endgame; source leaves nomination ownership unstated. Preserves human authorship and original recipient.

Alternatives: Girls collectively nominate; A Girl volunteers and Handler confirms

Implementation: The original Handler selects one actual original Cadre Girl; that Girl exclusively writes the Tag and account. Retain the exact source identities.

Change impact: Changing this ruling requires review of pending source-owned choices; preserve committed receipts and resources.


### `budget-persistent-tag-use-scope`

Source: Rulebook PDF152/printed150 Endgame5; PDF11/printed9.

Not removed when used means actual Handler Tag favour/attention/compel consumption. It grants no immunity to independently legal erase/conversion effects and does not clear an owed rejection by falsely claiming the Tag was removed.

Rationale: Specific printed HandlerTag consumption exception; no general indestructibleTag is printed.

Alternatives: Treat Tag as globally indelible until Handler death

Implementation: Not removed when used means actual Handler Tag favour/attention/compel consumption. It grants no immunity to independently legal erase/conversion effects and does not clear an owed rejection by falsely claiming the Tag was removed.

Change impact: Changing this ruling requires review of pending source-owned choices; preserve committed receipts and resources.


### `budget-gift-original-person-endings`

Source: Rulebook PDF152/printed150; original-person lifecycle source contracts.

The nominated living original Girl retains descriptive gift authorship after actual retirement/custody, without successor resources. Actual original Girl death or Handler source-role ending is reviewed from immutable history and closes the impossible pending gift without transferring its benefit/cost to a successor.

Rationale: Preserve actual original person; no source authorizes recipient substitution or automatic successor inheritance.

Alternatives: Keep an impossible source duty pending indefinitely; Nominate a different Girl/Handler after ending with new explicit source agreement

Implementation: The nominated living original Girl retains descriptive gift authorship after actual retirement/custody, without successor resources. Actual original Girl death or Handler source-role ending is reviewed from immutable history and closes the impossible pending gift without transferring its benefit/cost to a successor.

Change impact: Changing this ruling requires review of pending source-owned choices; preserve committed receipts and resources.


### `budget-collective-tag-period-trigger`

Source: Rulebook PDF152/printed150.

One optional collective Tag per actual OffDutyperiod afteratleastone genuineordinaryGoOffDuty result occurringafterthisEndgame; observation-only doesnotinventthe namedtrigger.

Rationale: Prevents multiplication perGirl while honoring the namedmove and Fromnowon timing.

Alternatives: One opportunity perindividualGoOffDutymove; Treat anyOffDutyroute includingObservation as sufficient

Implementation: One optional collective Tag per actual OffDutyperiod afteratleastone genuineordinaryGoOffDuty result occurringafterthisEndgame; observation-only doesnotinventthe namedtrigger.

Change impact: Changing this ruling requires review of pending source-owned choices; preserve committed receipts and resources.


### `budget-collective-tag-exact-consensus`

Source: Rulebook PDF152/printed150.

A Girl proposes an exactlabel/account andimplicitlyagrees byher explicitproposal; everyotheroriginalperiodGirl mustexplicitlyagree. Anydecline givesnoTag. Proposer maywithdraw andstartanew exactproposal; priorvotesnevercarrytonewwording.

Rationale: Printedcollectively leaves mechanismunstated; preserves voluntaryhuman authorship and no forgedconsent.

Alternatives: Majorityvote; OutofbotconsensusattestedbyoneGirl

Implementation: A Girl proposes an exactlabel/account andimplicitlyagrees byher explicitproposal; everyotheroriginalperiodGirl mustexplicitlyagree. Anydecline givesnoTag. Proposer maywithdraw andstartanew exactproposal; priorvotesnevercarrytonewwording.

Change impact: Changing this ruling requires review of pending source-owned choices; preserve committed receipts and resources.


### `budget-collective-tag-optional-lifetime`

Source: Rulebook PDF152/printed150 and explicit actualOffDutylifecycle.

Unusedlatentoption doesnotblockperiodcompletion andisno longeravailableafterrealperiodend; a human-started proposal createsreal requiredvote work untilresolved/withdrawn. No timeoutchoosesorlabelsforaplayer.

Rationale: Anoptional may-rule isnot mandatorywork untilhumans initiate its coordination.

Alternatives: RequireeachGirltoexplicitlydecline everyperiod; Allowoldoptionalopportunitiesindefinitely

Implementation: Unusedlatentoption doesnotblockperiodcompletion andisno longeravailableafterrealperiodend; a human-started proposal createsreal requiredvote work untilresolved/withdrawn. No timeoutchoosesorlabelsforaplayer.

Change impact: Changing this ruling requires review of pending source-owned choices; preserve committed receipts and resources.


### `budget-collective-tag-source-persons`

Source: Rulebook PDF152/printed150 and original-person lifecycle contracts.

BindtoactualoriginalHandler andperiodGirls, withproposerrecordedasordinaryTagprimarygiver andfull actualconsentcohort recorded. Provenoriginalendingscanbeexplicitlyreviewed; no automatic successorinheritance or consentbyUID.

Rationale: The source says you without granting successors its entitlement; explicitsourceprovenance preserves printedhuman decisions.

Alternatives: Cadre-wideentitlementtransfersautomatically tonewHandler; TreatallcohortmembersascoequalTagsetters in a futureextendedTagmodel

Implementation: BindtoactualoriginalHandler andperiodGirls, withproposerrecordedasordinaryTagprimarygiver andfull actualconsentcohort recorded. Provenoriginalendingscanbeexplicitlyreviewed; no automatic successorinheritance or consentbyUID.

Change impact: Changing this ruling requires review of pending source-owned choices; preserve committed receipts and resources.


### `virus_immediate_pain_restraint`

Source: [{"document": "rulebook", "pdf_page": 80, "printed_page": 78}].

Pain remains only through the actual immediate Punishment chain; Helpless uses ordinary real recovery.

Rationale: The source grants an immediate EI result and intolerable pain without duration or physical hands; a permanent source grip would invent contact and indefinite custody.

Alternatives: Permanent pain; invented hands-grasp; ending all Helpless on Punishment completion.

Implementation: Typed PainRestraint closes from actual RoleCase completion or original ending, never moves bodies or heals real Helpless.

Change impact: Changing this affects restraint duration and existing pending purges.


### `virus_fixed_eleven`

Source: [{"document": "rulebook", "pdf_page": 80, "printed_page": 78}].

Resolve the printed fixed 11 as a deterministic high EI effect without RNG, faces, Heat or a dice receipt.

Rationale: A rule-assigned result is already determined; synthetic dice would misrepresent provenance and permit inappropriate spending/modifiers.

Alternatives: Manufactured dice receipt; new roll with modifier.

Implementation: Canonical purge effect plus actual instruction/Punishment workflow, operational root receipt is None.

Change impact: Changing this alters audit format and would require a distinct source-aware roll rule.


### `harpy_ei_girl_side`

Source: [{"document": "rulebook", "pdf_page": 80, "printed_page": 78}, {"document": "rulebook", "pdf_page": 79, "printed_page": 77}, {"document": "rulebook", "pdf_page": 178, "printed_page": 176}, {"document": "rulebook", "pdf_page": 181, "printed_page": 179}].

Actual Harpy receives EI/fixed11 Helpless, while retaining the printed Receive Orders exemption.

Rationale: Combined Girl/Frame rules and the explicit Orders exception do not establish a separate EI immunity.

Alternatives: Infer blanket EI immunity from Battle category harpy.

Implementation: Exact ActorRef Helpless, no source category changes for unrelated Battle rules.

Change impact: Changing interpretation affects genuine Harpy targets; no Gorgon Helpless is added.


### `virus_girl_self_purge`

Source: [{"document": "rulebook", "pdf_page": 80, "printed_page": 78}].

Self-touch removes own actual infection without a self-superior order.

Rationale: No distinct recipient exists to receive a higher-Status order.

Alternatives: Invent self hierarchy or self Receive Orders.

Implementation: Actual purge event retains self-contact and grants no order/Status change.

Change impact: Changing affects self-purge bonus only.


### `virus_frame_self_purge`

Source: [{"document": "rulebook", "pdf_page": 80, "printed_page": 78}].

Self Frame purge still requires Handler-instructed actual self-Punishment and finite pain, with no self-Helpless or self-Bond.

Rationale: The immediate consequence is printed without an exception; self opposition is not a second person.

Alternatives: Waive consequence; invent self foe/grip; block legal self purge.

Implementation: Source-specific RoleCase self exception, real admissible effects; invalid self-Bond/last-Asset self-Helpless options excluded.

Change impact: Changing affects current self cases and punishment eligibility.


### `handler_girl_no_rank_disobey`

Source: [{"document": "rulebook", "pdf_page": 80, "printed_page": 78}, {"document": "rulebook", "pdf_page": 23, "printed_page": 21}, {"document": "rulebook", "pdf_page": 192, "printed_page": 190}].

Record real witnessed refusal without lowering nonexistent Status, while keeping actual Heat/Identity/Tag and discovered Punishment outcomes.

Rationale: Director-context Girl has genuine Girl resources but no canonical Cadre rank to lower.

Alternatives: Invent rank; skip whole witnessed outcome; proxy a PC sheet.

Implementation: Source-only actual ActorPlay Disobey, witness fact and unchanged rank, genuine frozen judge decision.

Change impact: Changing requires a real Status model and migration, not a numeric UID alias.


### `virus_past_link_factual_exposure`

Source: [{"document": "rulebook", "pdf_page": 80, "printed_page": 78}].

Allow append-only factual past-link exposure only with actual original linker, Frame owner and frozen judge and an earlier immutable already-infected episode.

Rationale: Accepted pre-existing histories may omit an actual link producer; chronology and separate original humans establish facts without rewriting history or granting present control.

Alternatives: Reject all pre-existing actual exposure; infer from shared human/current cast; retroactive infection.

Implementation: Original body/Frame/incarnation and source event authenticated; proposal then owner confirmation then judge review; unknown cells remain unknown.

Change impact: Changing affects accepted factual exposure sources, not current Frame permissions.


### `virus_vacancy_review`

Source: [{"document": "rulebook", "pdf_page": 80, "printed_page": 78}].

No link record is unknown, not proof of vacancy. Cure a genuinely reviewed empty Frame without target or bonus.

Rationale: The source affects a linked Pilot but cannot create one; incomplete pose records cannot justify silently evading that consequence.

Alternatives: Treat missing row as empty; invent Pilot; forbid known-empty cure.

Implementation: Actual owner proposes current facts and actual judge reviews; existing assigned original may be linked with unknown cells but no new body/Frame/control.

Change impact: Changing affects no-link review and fixed11 target selection.


### `gorgon-dormant-attacker-real-world-void`

Source: Rulebook PDF 19, 162, 165.

Actual attacker controller selects one existing uncorrupted World Gorgon Asset and rewrites its Void alteration. Preserve source Asset ID/family/damage and all unrelated resources. No human Pilot, Frame, Heat or Harpy resource is fabricated.

Rationale: The Dormant counter addresses the attacker, and actual Gorgon Assets already have a sole World authority with Void flags. No separate Gorgon transformation threshold is printed.

Alternatives: Reject all Gorgon-to-Dormant interaction permanently.; Charge the controller human’s unrelated Pilot.; Invent a new Void Asset or force a Harpy transformation.

Implementation: Actual attacker controller selects one existing uncorrupted World Gorgon Asset and rewrites its Void alteration. Preserve source Asset ID/family/damage and all unrelated resources. No human Pilot, Frame, Heat or Harpy resource is fabricated.

Change impact: Replaces the explicit pre-lock unsupported-target gate with a real owner-held immediate corruption and then the original contest. Requires actual source-history proof; no new RNG.


### `gorgon-dormant-already-fully-void`

Source: Rulebook PDF 19, 165.

Record actual already_fully_void only when a nonempty source-proven set is all Void. No repeat corruption, new Asset, healing, transformation or false Frame consequence. Empty/unknown resources remain gated.

Rationale: The ordinary Void procedure selects an uncorrupted existing Asset. With none present, inventing a new resource or using another fictional body changes the printed resource authority.

Alternatives: Invent another asset to corrupt.; Silently skip the required source counter without a canonical outcome.; Leave the debt forever pending despite complete actual resource proof.

Implementation: Record actual already_fully_void only when a nonempty source-proven set is all Void. No repeat corruption, new Asset, healing, transformation or false Frame consequence. Empty/unknown resources remain gated.

Change impact: Finite source-proven counter outcome with unchanged original assets. Further printed effects would require a separate source module.


### `gorgon-dormant-no-fabricated-frame-dive`

Source: Rulebook PDF 24, 162, 165.

Record dive_eligible=false and reason gorgon_has_no_frame_play for this actual Gorgon cost. Do not create a proxy Pilot/Frame or roll an unsupported Dive. Existing actual Pilot/Harpy forced-Dive paths remain source-owned.

Rationale: Dive Deep is a Frame Play. A Gorgon body and its World Assets are not an actual Girl piloting a separate Frame; the source does not define that conversion here.

Alternatives: Invent a Gorgon Frame/Heat/Identity and use Pilot mechanics.; Treat the human controller’s unrelated Pilot as the attacker.; Permanently gate any contact even when the concrete counter can be completed.

Implementation: Record dive_eligible=false and reason gorgon_has_no_frame_play for this actual Gorgon cost. Do not create a proxy Pilot/Frame or roll an unsupported Dive. Existing actual Pilot/Harpy forced-Dive paths remain source-owned.

Change impact: Explicit bounded source interpretation for review; does not claim a general Gorgon Dive or independent get-close implementation.


### `dormant-own-actual-basic-play-awakens`

Source: Rulebook PDF 162, 165.

A genuine declared and advanced/approved basic Attack, Collateral or Warp records one persistent cause=own_play marker for that same actual Gorgon. Menu/unstarted/cancelled intentions do not awaken it. No attack-induced Void debt is created by its own action.

Rationale: The actual advanced effect demonstrates activity, while Dormant’s printed retaliatory Void cost is specifically induced by forced awakening through attack. A declaration flag alone is no fictional effect.

Alternatives: Keep the actually acting Gorgon dormant until another actor attacks it.; Wake from merely viewing a menu or an abandoned intent.; Charge attack-induced Void to itself or a controller-owned Pilot.

Implementation: A genuine declared and advanced/approved basic Attack, Collateral or Warp records one persistent cause=own_play marker for that same actual Gorgon. Menu/unstarted/cancelled intentions do not awaken it. No attack-induced Void debt is created by its own action.

Change impact: Future actual attacks prove immutable source history and avoid duplicate awakening/cost. Existing already-owed counter debt is never cancelled or repaid; class/body/position unchanged. No timer or RNG.


### `leviathan-two-real-flesh-layer-assets`

Source: Rulebook PDF 164, 174.

An actual chosen protection Play adds exactly two real flesh-layer World Assets to the original living Leviathan once. Track only their ordinary current/destroyed Asset state through source-bound ID pointers. A Type label alone supplies no layer effect; a repeat call never resets damaged/destroyed layers.

Rationale: PDF174 says both flesh layers count as Assets. The existing Asset authority and ordinary Core-protecting Asset rules supply concrete damage/destruction consumers; an extra numerical armor pool would duplicate them.

Alternatives: Treat the printed circles as separate HP alongside mechanical Assets.; Automatically add/reset layers whenever the Type label is read.; Reallocate existing Class Asset slots to layers without an actual chosen action.

Implementation: An actual chosen protection Play adds exactly two real flesh-layer World Assets to the original living Leviathan once. Track only their ordinary current/destroyed Asset state through source-bound ID pointers. A Type label alone supplies no layer effect; a repeat call never resets damaged/destroyed layers.

Change impact: Two genuinely targetable Assets with preserved current resources/positions. Initial legacy serialization unchanged while pointer fields are absent. New grants require independent source review; no production ungate.


### `leviathan-piercing-and-conjunctive-core`

Source: Rulebook PDF 15, 164, 174.

Actual ordinary Asset damage or source destruction pierces that exact layer. Both layers and all original Core-plan guards must be dealt with; the actual original weakness must still be confirmed. No second piercing counter or HP is tracked.

Rationale: The source defines the layers as Assets rather than providing a new damage procedure. Existing ordinary Gorgon Core guards already use damaged or actually destroyed Assets.

Alternatives: Require destruction only despite ordinary Asset damage.; Allow one layer or the original guard condition to replace all remaining guards.; Accept a narrative pierced flag that leaves the real Asset intact.

Implementation: Actual ordinary Asset damage or source destruction pierces that exact layer. Both layers and all original Core-plan guards must be dealt with; the actual original weakness must still be confirmed. No second piercing counter or HP is tracked.

Change impact: Existing AllOut/Gorgon-contest effects change the real source Assets, and raw World exposure plus new Core admission enforce their conjunction.


### `leviathan-protection-future-source-only`

Source: Rulebook PDF 26, 174.

Raising actual layers closes the currently exposed Core for future declarations and makes unrolled snapshots stale. It cannot recalculate an already-rolled original strike, retroactively add a modifier, undo frozen required death, or harm a successor instead.

Rationale: The actual source resources and exposure change now. Receipt/source identity remains immutable, and the existing fatal-hit timing is already frozen at the real original strike.

Alternatives: Let new layers cancel a known fatal receipt.; Leave the Core available to new strikes despite the new intact layers.

Implementation: Raising actual layers closes the currently exposed Core for future declarations and makes unrolled snapshots stale. It cannot recalculate an already-rolled original strike, retroactively add a modifier, undo frozen required death, or harm a successor instead.

Change impact: New exposure/strike requires genuine piercing; existing original fatal effects preserve their source. The trusted after-roll composition test is not a claim that a generic Type-counter menu is implemented.


### `beyond-intense-source-legal-no-heat`

Source: Rulebook PDF 11.

Preserve real Intense Bonds for every otherwise source-legal participant, including NPCs and actual Gorgons. Beyond-depth deepening grants +2 only to actual Heat-bearing participants; never invent Heat or suppress an independently required Gorgon/Void source.

Rationale: A relationship does not by itself create a Heat resource or override an independently required consequence.

Alternatives: Exclude any participant lacking Heat, or invent a proxy Heat resource.

Implementation: Preserve real Intense Bonds for every otherwise source-legal participant, including NPCs and actual Gorgons. Beyond-depth deepening grants +2 only to actual Heat-bearing participants; never invent Heat or suppress an independently required Gorgon/Void source.

Change impact: No ordinary NPC/Gorgon silently disappears from otherwise legal source choices; actual ActorRefs and existing eligibility remain authoritative.


### `mockingbird-sex-self-asset-family`

Source: Rulebook PDF 36, 15.

A Void Asset written on the Girl herself through the middle collect result is a Girl Asset, follows the actual four-Asset cap, and requires explicit eligible replacement when full.

Rationale: An Asset explicitly written on the Girl uses the existing Girl Asset authority and capacity.

Alternatives: Let the player choose Frame family without a Frame-specific source or ignore the cap.

Implementation: A Void Asset written on the Girl herself through the middle collect result is a Girl Asset, follows the actual four-Asset cap, and requires explicit eligible replacement when full.

Change impact: No extra free capacity, concealed replacement, repair or copied asset; sole source Void is removed only atomically with the actual destination.


### `mockingbird-sex-already-fully-void`

Source: Rulebook PDF 36, 19.

A mandatory high result against an actual already fully Void Harpy records the factual saturated outcome and real Bond/risk; do not manufacture another Asset, repeat conversion or a fake patient acknowledgment.

Rationale: A mandatory corruption cannot select an uncorrupted resource when no such resource remains.

Alternatives: Force an impossible new uncorrupted choice or rerun an already completed conversion.

Implementation: A mandatory high result against an actual already fully Void Harpy records the factual saturated outcome and real Bond/risk; do not manufacture another Asset, repeat conversion or a fake patient acknowledgment.

Change impact: One actual source receipt; original resources preserved. Voluntary Risk still needs a real unvoid Asset cost.


### `mockingbird-sex-group-primary`

Source: Rulebook PDF 36.

For an actual multi-participant interaction, the caster explicitly chooses one primary printed counterpart; all actual source participants independently attest. Collect can redirect only among those real participants.

Rationale: The singular printed counterpart does not specify how to select among multiple actual participants.

Alternatives: Automatically choose the first account or grant every participant every primary consequence.

Implementation: For an actual multi-participant interaction, the caster explicitly chooses one primary printed counterpart; all actual source participants independently attest. Collect can redirect only among those real participants.

Change impact: Human intent owns the original counterpart; no guessed fictional interaction or hidden target substitution.


### `mockingbird-sex-discovery-not-omniscience`

Source: Rulebook PDF 36.

Undisclosed risk does not automatically inflict Punishment. Actual source participants may report a current known witness; that real witness attests and the original source Handler confirms discovery. Low conditional Tag is authored only then.

Rationale: Procedural access to private state does not establish fictional discovery by a Handler.

Alternatives: Treat procedural GM/database knowledge as in-fiction discovery or auto-inflict Punishment.

Implementation: Undisclosed risk does not automatically inflict Punishment. Actual source participants may report a current known witness; that real witness attests and the original source Handler confirms discovery. Low conditional Tag is authored only then.

Change impact: Private source material remains private; no generated intimate acts, false discovery or successor Handler authority.


### `mockingbird-starry-original-body-lifetime`

Source: Rulebook PDF 35, 36, 192.

The extra capability lasts while the exact Starry-Eyed Tag remains on that actual counterpart. Proven same Handler body across a Director rules-context ending retains it; a successor body does not.

Rationale: The printed capability depends on the Tag on its original recipient, rather than a temporary rules context.

Alternatives: Expire at context ending or grant it to every later role under the same human account.

Implementation: The extra capability lasts while the exact Starry-Eyed Tag remains on that actual counterpart. Proven same Handler body across a Director rules-context ending retains it; a successor body does not.

Change impact: Immutable original gift/source remains; current capability derives from actual original Tag and same-body proof.


### `call-guest-source-one-effect`

Source: Rulebook PDF 24, 35.

The original caster invites a real nearby source person; the actual original human accepts boarding. That guest owns exactly one applicable original Dive consequence, including actual table-owned answers/agreement. The original roll stays held through real consequences, without another roll or generic borrowed FramePlay access.

Rationale: The named invitation grants a specific consequence without granting a second Frame or a general Play entitlement.

Alternatives: Automatically board another player or grant guest a copied Frame/stat pool and independent Plays.

Implementation: The original caster invites a real nearby source person; the actual original human accepts boarding. That guest owns exactly one applicable original Dive consequence, including actual table-owned answers/agreement. The original roll stays held through real consequences, without another roll or generic borrowed FramePlay access.

Change impact: No manufactured consent, duplicated RNG/Heat, wrong-body resources or unrestricted guest entitlement.


### `call-nearby-communication-source`

Source: Rulebook PDF 35.

Known same-cell or real source co-presence establishes nearby; relay transmits a player-authored message and the actual Gorgon human owns response or silence. Communication alone does not reveal hidden map entities, compel truth or expose the mental exchange to unrelated table humans.

Rationale: The source gives communication without a numeric range, automatic discovery or compelled response.

Alternatives: Invent grid radius, automatic hidden-Gorgon discovery, AI reply or compelled honesty.

Implementation: Known same-cell or real source co-presence establishes nearby; relay transmits a player-authored message and the actual Gorgon human owns response or silence. Communication alone does not reveal hidden map entities, compel truth or expose the mental exchange to unrelated table humans.

Change impact: Preserves existing source geography and private knowledge; no fictional joins or new permissions.


### `call-guest-physical-help`

Source: Rulebook PDF 24, 35.

Voluntary boarding needs actual free capable bodies, exact current unlocked carrier cockpit and paired source contact acceptance. Subsumption affects the actual guest body/occupied Frame; real Frame consent and a physically present other role perform extraction. Inactive vital signs persist until actual medical help is reported and factually confirmed.

Rationale: The existing boarding, Core consent and medical rules require actual bodily actions and separate human authority.

Alternatives: Use Defeat rescue authority, automatic recovery/transport, copied own Frame occupancy or account-based Frame consent.

Implementation: Voluntary boarding needs actual free capable bodies, exact current unlocked carrier cockpit and paired source contact acceptance. Subsumption affects the actual guest body/occupied Frame; real Frame consent and a physically present other role perform extraction. Inactive vital signs persist until actual medical help is reported and factually confirmed.

Change impact: No fabricated movement, healing, capacity or successor body authority; current JANUS voice can be a different actual human from the Pilot and procedural Handler.


### `leviathan-specific-tag-cost`

Source: Rulebook PDF174/printed172 and PDF11/printed9.

The Type trigger may mark the actual subject’s obsessed Tag even when its controller also controls another body. This cost grants no ordinary Tag modifier; ordinary modifiers retain their separate human/scene restrictions.

Rationale: The specific compulsory trigger names a Tag cost, while the general modifier has different eligibility.

Alternatives: Apply the ordinary other-human modifier restriction to the Type cost.

Implementation: Source-owned Leviathan reducers, real shared action/receipt flow and private native choices; unsupported intersections remain gated.

Change impact: Review pending original-source choices before changing this interpretation; preserve known dice, existing resources and original ownership.


### `leviathan-protected-ordinary-identities`

Source: Rulebook PDF174/printed172 and PDF58/printed56.

The high result replaces actual eligible ordinary slots while preserving protected extras and another person’s Paired Identity. Missing or lost slots are not invented.

Rationale: Explicit protection from another person changing a Paired Identity constrains the broader four-Identity result.

Alternatives: Replace protected extras or create four slots regardless of actual resources.

Implementation: Source-owned Leviathan reducers, real shared action/receipt flow and private native choices; unsupported intersections remain gated.

Change impact: Review pending original-source choices before changing this interpretation; preserve known dice, existing resources and original ownership.


### `leviathan-multiple-source-locks`

Source: Rulebook PDF174/printed172.

Reusing an existing obsessed Identity retains every real source lock. Only the corresponding source’s actual recorded death releases its restriction; leaving a map does not count as death.

Rationale: A second source effect does not state that it cancels the first source’s until-death condition.

Alternatives: Allow the newest source to replace all prior restrictions.

Implementation: Source-owned Leviathan reducers, real shared action/receipt flow and private native choices; unsupported intersections remain gated.

Change impact: Review pending original-source choices before changing this interpretation; preserve known dice, existing resources and original ownership.


### `leviathan-heat-gain-scope`

Source: Rulebook PDF174/printed172.

An obsessed subject gains Heat only through a qualifying marked obsessed Identity. Other positive gains are recorded as blocked; legal spending and negative adjustments retain their normal rules. No Heat pool is created for a role without one.

Rationale: The source restricts gains, without canceling unrelated valid effects or creating new resources.

Alternatives: Cancel the entire action that otherwise grants Heat, or remove existing Heat.

Implementation: Source-owned Leviathan reducers, real shared action/receipt flow and private native choices; unsupported intersections remain gated.

Change impact: Review pending original-source choices before changing this interpretation; preserve known dice, existing resources and original ownership.


### `leviathan-low-actual-arrival`

Source: Rulebook PDF174/printed172.

The low result completes through actual subject/mover and adjudicator confirmation of travel along the influence trail. Apply the existing body/controlled Frame position authority; preserve parked Frames and unknown endpoints. Physical blockers require their real source operation.

Rationale: The endpoint is compulsory, but no extraction, control transfer or transport permission is granted.

Alternatives: Teleport the subject and its assigned Frame without control or custody review.

Implementation: Source-owned Leviathan reducers, real shared action/receipt flow and private native choices; unsupported intersections remain gated.

Change impact: Review pending original-source choices before changing this interpretation; preserve known dice, existing resources and original ownership.


### `leviathan-roll-resource-order`

Source: Rulebook PDF174/printed172 and PDF11/printed9.

Succumb uses two real dice plus the subject’s actual Tag count, without Heat spending or a proxy character. Pay the trigger Tag and resolve any required repeated-Tag response before counting Tags and rolling; preserve normal post-roll Tag choices.

Rationale: The specified roll modifier comes from the affected person’s actual resources after the committed trigger cost.

Alternatives: Count removed Tags or spend the controller’s unrelated Pilot Heat.

Implementation: Source-owned Leviathan reducers, real shared action/receipt flow and private native choices; unsupported intersections remain gated.

Change impact: Review pending original-source choices before changing this interpretation; preserve known dice, existing resources and original ownership.

### `budget-ruin-map-condition`

Source: rulebook PDF152/printed150. Two ruined locations use the existing destroyed condition, emit actual structure-loss triggers and preserve required last-base aftermath. This avoids a second map-condition authority; alternatives are narrative-only ruin or a distinct new condition. Implemented by RuinService and owned native selection. Changing it requires reviewing pending selections and preserving committed sources. Delegated recommendation; printed-rule clarity review pending.

### `budget-photoshoot-public-setter`

Source: rulebook PDF150/printed148. The appointed human records one public-perception Tag for each original Girl after the real photoshoot, using authenticated OOC setter provenance. No fictional Handler knowledge, extra public NPC or numeric funds are created. The printed event leaves the public setter representation unspecified; alternatives are an actual public NPC or the fictional Handler as giver. Existing typed Strain/native controls implement this, guarded by original period character IDs. Any adjustment must preserve committed Tag provenance and review pending effects. Delegated recommendation; printed-rule clarity review pending.

### `budget-rich-patron-source-visits`

Source: rulebook PDF150/printed148. The real rich patron gains a Personal Bond with the selected original Girl; preserve a deeper existing Bond. Its actual controller reports a real visit and evidence actually seen before authoring a Tag for the original Handler. Private database access is not fictional observation. Alternatives are automatic deepening or inferring evidence from private history. Source-proved patron records, canonical Actor Bonds and owner-only native visit controls implement this without invented movement or player conduct. Adjustments must preserve original bindings and Tag provenance. Delegated recommendation; printed-rule clarity review pending.

## JANUS source clarifications — normal workflow checkpoint

All remain delegated recommendations requiring printed-rule clarity review. Storage is a partial consumer and stays unavailable for purchase.

### `janus_original_core_admission`

Source: Official rulebook PDF68/printed66; normalHarpy PDF178.

Admit a distinct original unnamed ex-Girl Core on the existing JANUS only after actual Pilot request, selected real human factual proposal and Foundation source review. No former PC/archive/new Frame/paid abilities. Unspecified existing body Heat, Identity names/marks, actual Girl Asset count/details/damage and appearance are actual controller-approved facts; no automatic2 Girl Assets.

Rationale: Printed original Core exists and functions as a normal Harpy but has no complete source sheet; facts must not be fabricated as former history.

Alternatives: Borrow an existing PC as the Core; Invent a former Pilot archive or resource package; Retain only four cosmetic strings

Implementation: Admit a distinct original unnamed ex-Girl Core on the existing JANUS only after actual Pilot request, selected real human factual proposal and Foundation source review. No former PC/archive/new Frame/paid abilities. Unspecified existing body Heat, Identity names/marks, actual Girl Asset count/details/damage and appearance are actual controller-approved facts; no automatic2 Girl Assets.

Change impact: One actual external_pilot identity and original body; source registry admission events and native response ownership; read old initialFrameIDs unchanged.

### `janus_single_frame_resource_exception`

Source: Official rulebook PDF68-69; normalHarpy PDF178.

Core Girl Assets follow normalHarpy Void physiology. The actual existing JANUS Frame Assets remain at their single original current/parked Frame authority and keep their source-known Void states; the book last-Tag erasure is the actual new Frame-wide corruption event.

Rationale: JANUS begins with a controlled Core and its ordinary2 chosen Frame Assets, while LivingBattery explicitly names later allFrame corruption. Copying/automatically corrupting that Frame at Core registration erases the printed distinction.

Alternatives: Copy all Frame Assets into a second Core pool; Force all initialJANUS Frame Assets Void on admission

Implementation: Core Girl Assets follow normalHarpy Void physiology. The actual existing JANUS Frame Assets remain at their single original current/parked Frame authority and keep their source-known Void states; the book last-Tag erasure is the actual new Frame-wide corruption event.

Change impact: Damage/corruption/destruction through either pilot/Core view updates exact sole origin. Core registration changes no existing Frame Assets or position.

### `janus_control_tags_live_semantics`

Source: Official rulebook PDF68.

The four original Tag IDs carry exact printed effects: Drugged means general sourceHelpless without invented opposing person, Restrained blocks actual Plays, Muzzled blocks physical speech, surgery is an actual pain Tag. Do not equate Muzzled with noPlays or erase independent Helpless sources when Drugged is removed.

Rationale: Each printed parenthesis is narrower than a generic incapacitation flag. Actual live Tag identity, not arbitrary wording, governs original baseline treatment.

Alternatives: Leave only label strings; Treat Drugged as death/inactive body; Treat Muzzled as unable to make anyPlay

Implementation: The four original Tag IDs carry exact printed effects: Drugged means general sourceHelpless without invented opposing person, Restrained blocks actual Plays, Muzzled blocks physical speech, surgery is an actual pain Tag. Do not equate Muzzled with noPlays or erase independent Helpless sources when Drugged is removed.

Change impact: Actual shared actor begin/preRoll/native restrictions; source Tag marker/private response and actual original Core remain separate from controller otherPC.

### `janus_frame_voice_human_not_conversation`

Source: Official rulebook PDF68-69; physical Frame consent source.

Resolve OOC Frame voice to its exact bound living original Core controller; JANUS without actual sourceCore setup fails closed. Returning the human ID does not prove spoken/mental fictional communication or consent. Muzzled remains; explicit real LivingBattery link is the printed direct mental exception.

Rationale: An unrelated current Handler or same-human otherPC cannot stand in for the actual original Core. Source authority and fictional communication/contact are separate proofs.

Alternatives: Fallback to current Handler; Borrow controller otherPC persona; Treat every Frame voice prompt as free Core telepathy

Implementation: Resolve OOC Frame voice to its exact bound living original Core controller; JANUS without actual sourceCore setup fails closed. Returning the human ID does not prove spoken/mental fictional communication or consent. Muzzled remains; explicit real LivingBattery link is the printed direct mental exception.

Change impact: Actual extraction/consent consumers must verify any required fictional request via real source contact/link; no names or ordinary speech inferred.

### `janus_distinct_actual_battery`

Source: Official rulebook PDF69-70 / printed67-68.

Use a distinct actual battery person. The same human may control both actual roles; no physical self-loop, self-Bond or invented private other-mind answer.

Rationale: The printed other-person trigger and contact need actual separate endpoints. Physical self-jack reach and self-result ownership are not specified.

Alternatives: Explicit future self-link module

Implementation: Use a distinct actual battery person. The same human may control both actual roles; no physical self-loop, self-Bond or invented private other-mind answer.

Change impact: Real ActorRefs and spinal contact; speaker ownership remains actual role-bound.

### `janus_battery_known_roll_and_current_low_tag`

Source: Official rulebook PDF69 / printed67.

Roll once per performed/reviewed spinal contact. Freeze actual pre-roll Tag IDs for +Tag modifier; erase one actual current Tag on low, including a genuinely acquired intervening Tag. Only an actual final Tag erasure triggers takeover.

Rationale: A known roll cannot repeat without new actual plugging, and a post-roll Tag change cannot rewrite the saved modifier.

Alternatives: Recount at final effect; Require only original Tags to be erased

Implementation: Roll once per performed/reviewed spinal contact. Freeze actual pre-roll Tag IDs for +Tag modifier; erase one actual current Tag on low, including a genuinely acquired intervening Tag. Only an actual final Tag erasure triggers takeover.

Change impact: Original receipt remains immutable; erasure stores its own actual before-Tag IDs.

### `janus_link_mental_assets_and_private_channel`

Source: Official rulebook PDF69 / printed67.

Harpy Cognition/Offset Emotional Load are exact additional mental Girl Assets bound to the actual selected benefit/link, without copying a Core-owned Asset or consuming ordinary four-Asset capacity. They expire on actual unlink/ending. The question option grants the actual two minds a private human-authored ongoing channel; it supplies no Handler knowledge or automatic answer.

Rationale: The book names additional mental Assets rather than lending existing body hardware, and explicitly permits free brain communication.

Alternatives: Borrow Core assets; Treat question as a single public answer

Implementation: Harpy Cognition/Offset Emotional Load are exact additional mental Girl Assets bound to the actual selected benefit/link, without copying a Core-owned Asset or consuming ordinary four-Asset capacity. They expire on actual unlink/ending. The question option grants the actual two minds a private human-authored ongoing channel; it supplies no Handler knowledge or automatic answer.

Change impact: One source pointer per additional Asset; no physical-item transfer, no duplicated base pool.

### `janus_pet_qualifying_roll`

Source: Official rulebook PDF70 / printed68.

Pet uses final8+ Living Battery against the actual original Harpy, with entitlement present at that raw roll, creating one next actual Off-Duty carry opportunity.

Rationale: Living Battery is the referenced JANUS roll; unrelated dice and retroactive purchases must not qualify.

Alternatives: Use Go Off-Duty8+ instead

Implementation: Pet uses final8+ Living Battery against the actual original Harpy, with entitlement present at that raw roll, creating one next actual Off-Duty carry opportunity.

Change impact: Original link/receipt/period proof retained; real owner choice, physical unplug, same original body and return required.

### `janus_pet_equipment_not_bonus_tag`

Source: Official rulebook PDF70 / printed68.

Pet grants actual Leash and Collar equipment/custody provenance, without inventing an extra Tag, mechanical Asset or +1 Battery modifier. Carrying changes no Frame assignment or known location by inference.

Rationale: The text says she gains Leash and Collar, without labeling either a Tag or Asset.

Alternatives: Count it as one extra Tag; Create a mechanical Girl Asset

Implementation: Pet grants actual Leash and Collar equipment/custody provenance, without inventing an extra Tag, mechanical Asset or +1 Battery modifier. Carrying changes no Frame assignment or known location by inference.

Change impact: Current typed outing records actual gear/body custody. Generic held-item transfer of this particular equipment remains a separate unsupported port.

### `janus_foundation_tag_replacement_identity`

Source: Official rulebook PDF68,70 / printed66,68.

Ordinary actual Off-Duty Foundation care restores the four printed control conditions with fresh source Tag identities; preserve other real personal Tags and immutable original admission IDs. A qualifying Pet carry postpones that treatment until the actual original body returns.

Rationale: New treatment must not inherit old Tag permissions/marks or rewrite creation history. Printed automatic replacement is an actual source effect, without fabricated player dialogue.

Alternatives: Reuse old removed Tag IDs; Replace every personal Tag; Apply treatment while a carried Core is away

Implementation: Ordinary actual Off-Duty Foundation care restores the four printed control conditions with fresh source Tag identities; preserve other real personal Tags and immutable original admission IDs. A qualifying Pet carry postpones that treatment until the actual original body returns.

Change impact: Current semantic mapping remains separate from original baseline provenance; body position is never changed by routine treatment.

### `janus_detached_body_resource_scope`

Source: Official rulebook PDF68-70 / printed66-68.

A detached unlinked original Core retains its real Girl Assets but cannot alter her former host Frame through a historical binding. Actual same-Frame Harpy rebirth, when source-proved, instead uses the resulting Harpy current Frame pool as sole shared hardware authority.

Rationale: Neither a historical owner label nor shared controller can transfer physical resource ownership.

Alternatives: Keep former host resources forever; Copy archived Frame resources into another pool

Implementation: A detached unlinked original Core retains its real Girl Assets but cannot alter her former host Frame through a historical binding. Actual same-Frame Harpy rebirth, when source-proved, instead uses the resulting Harpy current Frame pool as sole shared hardware authority.

Change impact: No old Frame damage through a detached Core; no Frame pool duplication or archive mutation.

### `janus-void-storage-separate-points`

Source: Rulebook PDF 70.

Newly gained stored Void is a separate source-owned point bound to its original actor, existing Asset, original Harpy and actual gain event. Its alteration is active only while the same Harpy is genuinely plugged in. Permanent Asset.void remains unchanged.

Rationale: The printed temporary-while-plugged wording must not allow unplugging to erase unrelated permanent corruption or actual prior conversion.

Alternatives: Mutate permanent Asset.void then reverse it on every unplug, or treat stored changes as permanent.

Implementation: Newly gained stored Void is a separate source-owned point bound to its original actor, existing Asset, original Harpy and actual gain event. Its alteration is active only while the same Harpy is genuinely plugged in. Permanent Asset.void remains unchanged.

Change impact: One sole stored point survives genuine unplug/replug; original permanent resources and required work retain their authority. Active projection does not duplicate an Asset.

### `janus-storage-actual-off-duty-surgery`

Source: Rulebook PDF 70.

The original patient requests one exact stored point after an actual Go Off-Duty receipt. The period's original Foundation human records performed surgery. At most one point per original patient is removed in that period, without damaging or repairing the original Asset.

Rationale: A period label or purchase alone is not performed surgery, and one printed removal must not become repeatable free removal.

Alternatives: Automatically delete a stored point on period activation, or permit repeated removals from the same period.

Implementation: The original patient requests one exact stored point after an actual Go Off-Duty receipt. The period's original Foundation human records performed surgery. At most one point per original patient is removed in that period, without damaging or repairing the original Asset.

Change impact: The optional request is resumable/private and does not invent personnel, transport, medical completion or an Asset repair.

### `political-function-disclosed-rights-lifetime`

Source: rulebook PDF150/printed148, Low Budget2.1. Original Girls receive the Tag-right notice, confirm their own real attendance and optionally author a Tag for their own actual out-of-line action while the function is active. The original Handler records its real ending, expiring that permission. This supplies the missing coordination/lifetime without generated dialogue, automatic attendance or conduct classification. Alternatives are automatic actions/Tags or unlimited post-function rights. Source-bound function/native controls and required work implement this; later adjustments must preserve original notices, confirmations and Tag sources. Delegated recommendation; printed-rule clarity review pending.

## Alpha, JANUS Storage and Budget workflow clarifications — 2026-11-05

Delegated recommendations below remain adjustable and flagged for printed-rule clarity review. Unsupported source branches remain implementation gaps.

### `alpha-low-real-play-conditional-broken`

Source: Rulebook PDF52 / printed50 Brutalize.

The original target chooses whether their genuine counter Play will leave the attacker Broken before starting it; apply Broken only after that real Play and its required choices finish. No success requirement is added.

Rationale: The text gives one opportunity and says if they can make a Play they can leave the attacker Broken; source-owned preselection prevents inventing a later human response.

Alternatives: Ask after completed Play through another owned choice; Require successful counter (unprinted restriction)

Change impact: Change conditional selection timing without reusing or rerolling the saved child receipt.

### `alpha-broken-original-relative-status`

Source: Rulebook PDF52 / printed50 Brutalize.

Broken is an original-person relation to its actual inflictor; it overrides relative PC Status while both originals remain current, without changing the global Status order.

Rationale: Printed text says lower Status relative to the inflictor, not a global rank loss.

Alternatives: Global rank reduction (does not preserve printed relativity)

Change impact: Original ActorRefs/source events retained. Reciprocal Broken remains unresolved/fail-closed rather than inventing precedence.

### `alpha-guard-unarmed-proof`

Source: Rulebook PDF52 / printed50 Brutalize and PDF190 Guard moves.

The admitted Guard controller reviews actual weapon facts before the roll. A low result gives the real owned counter opportunity first; afterward the original Alpha may explicitly spare or kill the reviewed unarmed NPC. Empty inventory alone never proves unarmed.

Rationale: Preserves both printed opportunity and optional unarmed killing without manufacturing NPC actions or weapons.

Alternatives: Kill before allowing counter; Infer unarmed from missing records

Change impact: Frozen factual assessment ID, actual source counter event and selected final response are retained.

### `alpha-npc-injury-canonical`

Source: Rulebook PDF52 / printed50 injury and existing NPC injury representation.

The actual Alpha authors the injury; persist it as a bounded actual injury Tag plus immutable source fact, with no invented NPC HP or Asset slots.

Rationale: Reuses the current canonical NPC injury representation and gives the actual physical consequence a saved consumer.

Alternatives: Narrative fact only, without Tag consumers

Change impact: Original NPC ID and actual injury label/event retained. No additional generic damage menu options granted.

### `alpha-original-npc-broken-orders`

Source: Rulebook PDF52 / printed50 and existing ReceiveOrders/Disobey.

An actual original NPC inflictor is superior to this original Broken Pilot for their own direct Orders. Store the actual NPC ActorRef and human controller separately; real mid Disobey may replace its ordinary option by removing only this exact condition.

Rationale: Applies printed relative Status and removal without borrowing the NPC controller's Handler/PC identity or inventing NPC Heat/dice.

Alternatives: Store controller as issuer (would grant another role false authority); Ignore actual NPC source Status/removal (would omit printed condition consumer)

Change impact: Immutable instruction, original condition/event, actual cast and issuer/controller retained in the existing Orders protocol. General NPC Orders remain gated.

### `alpha-sex-finite-sleep-opportunity`

Source: Rulebook PDF53 / printed51 low Alpha Sex.

Persist source sleep independently of injury and Helplessness. Keep the original counterpart opportunity pending until explicitly declined or actually performed, then require the original Alpha to record waking. Safety pause remains available.

Rationale: The text gives an actual opportunity while Alpha sleeps but no duration; this prevents a free wake bypass while avoiding automatic invented recovery.

Alternatives: Automatically wake on result (would erase opportunity); Permanent unconscious injury (unprinted harm)

Change impact: Original sleep/effect/wake events and source controllers retained; changing duration must preserve performed outcomes.

### `alpha-sex-no-reprisal-scope`

Source: Rulebook PDF53 / printed51 low Alpha Sex.

The source opponent may exercise one real supported opportunity without a reprisal Play from the sleeping Alpha. This creates no permanent immunity, self-Helpless relation or waived safety/other printed consultation.

Rationale: Consumes the printed one opportunity while retaining actual source effects, existing required followups and ordinary rules afterward.

Alternatives: Automatic harm immunity; Treat mere opportunity selection as actual performance

Change impact: Actual child/transfer/RoleCase receipts and completion source remain authoritative.

### `alpha-sex-distinct-broken-tracking`

Source: Rulebook PDF53 / printed51 mid Alpha Sex.

Keep this Play's own Broken source even if the same inflictor already has another active Broken source. The relation lowers Status once; exact scent entitlement lasts only while this Play's condition remains active. A real eligible Disobey removes Broken against that inflictor, including its active occurrences.

Rationale: Avoids fabricating scent authority from a different earlier Play or erasing historical provenance.

Alternatives: Overwrite the prior source; Grant scent from any old Broken condition

Change impact: Each source condition has a stable ID/action/event. Original source remains history after removal.

### `alpha-sex-scent-actual-location`

Source: Rulebook PDF53 / printed51 scent tracking.

The owner may privately discover the actual current original body location by scent while the exact source condition is active. It performs no movement and invents no coordinates when factual position is unknown/offstage.

Rationale: Provides a real discovery consumer without teleporting either person or substituting the target controller's other character.

Alternatives: Automatic movement; Invent narrative position

Change impact: A future physical tracking/travel consumer can reuse the exact source condition and actual body provenance.

### `janus-storage-effective-threshold-lifetime`

Source: Rulebook PDF 19, 70.

Active stored alterations count toward actual effective all-Void conditions while genuinely plugged in. Actual unplug/removal can end an uncompleted consequence whose sole full-family cause ceased, while any remaining full cause continues. Completed transformation and permanent Void are never reversed.

Rationale: The temporary-while-plugged wording changes whether the printed all-Assets condition currently exists; it does not rewrite completed physical history.

Alternatives: Ignore stored points in all-Void counts, or make every started consequence permanent even after its only conditional cause disappears.

Change impact: Reuse existing Void/Keep/consent mechanics with exact stored-point pointers; no second birth lifecycle or reversible completed transformation.

### `janus-storage-reconnect-producer`

Source: Rulebook PDF 69, 70.

A genuine new spinal plugging uses its actual Living Battery source producer. Prior stored changes activate only after that completed connection effect, including any required owned private answer. No additional Storage RNG or fabricated new gain is created.

Rationale: The actual connection and its known receipt remain authority; a manually flipped link flag or unrelated relink does not reactivate stored effects.

Alternatives: Activate from an unproved flag, or require a separate Storage-specific roll on each reconnect.

Change impact: Reconnect has one genuine source episode and can reopen the normal conditional Void consequence without duplicated dice.

### `janus-storage-explicit-void-creation-boundary`

Source: Rulebook PDF 19, 29, 69, 70.

Explicit Defeat growth of two new Void-corrupted Assets and forced all-Frame Core takeover remain permanent printed creations/effects. Generic Void rewrite gains offer optional Storage. Their threshold readers still count already active stored alterations.

Rationale: These clauses explicitly create or corrupt specified hardware rather than invoking the generic choice to rewrite one uncorrupted Asset; diverting them would alter their stated effects.

Alternatives: Treat every Void-labelled creation or forced whole-Frame corruption as one divertible generic gain.

Change impact: No new Defeat diversion UI, no optional waiver of actual takeover, and no stored point can undo a permanent result.

### `budget-director-performance-source`

Source: Rulebook PDF151/printed149 and PDF192/printed190.

A separately played Director owns the actual appearance and departure; the original Handler owns its two fresh context Identities or reuses the already active context. The event adds four Heat once to the actual Handler context after it is established, subject to existing source Heat restrictions.

Rationale: The Budget event grants Heat while the Director rules require the Handler to use a distinct Girl-rule pool. Applying the event to another PC or before the context reset would lose its source effect.

Alternatives: Give the Heat to a different PC.; Apply four Heat before resetting the context to zero.

Change impact: Preserve original meeting/context/Heat events. Existing non-context Identity carry remains unavailable pending its actual source port.

### `budget-candidate-table-process`

Source: Rulebook PDF151/printed149 and PDF191/printed189.

Keep the existing NPC body, controller and other jobs when assigning Pilot Candidate. The original table, including its controller and assigned Girl, authors and agrees to one exact process; edits clear prior agreements. Only the assigned original Girl reports its actual assessment. The assessment never automatically activates a player character or grants resources.

Rationale: The source assigns the assessment and requires the table to define candidacy, without a numeric check or success package. Exact proposals preserve each human contribution and avoid invented conversion mechanics.

Alternatives: Let one human silently define everyone else's process.; Auto-create a PC or reward package when the process is agreed.

Change impact: Review original participant/process agreements before adjusting table composition. Preserve assignment, authored process, actual report and source history.

### `budget-anarchy-conditional-city-order`

Source: Rulebook PDF151/printed149.

Anarchy is an exact source blockage that makes the city nonoperational while retaining its physical condition. Supported city-use and world-advancement consumers use that condition. The original Handler records an actual method and established civic outcome to remove only this source cause. It repairs no physical destruction and grants no Gorgon territory.

Rationale: The printed city counts as destroyed only until order is restored. A permanent physical destruction or map-only flag would omit either its temporary lifetime or actual mechanical consumers; no special pacification die is printed.

Alternatives: Permanently destroy the physical city.; Keep the condition in the map display only or clear it from a planned action.

Change impact: Preserve previous physical damage and every unrelated blocked source. Future city consumers must use the same operational condition; narrative plans do not constitute restored order.

## DoctorDoctor normal workflow interpretations — 2026-11-05

Delegated recommendations; printed-rule clarity review remains pending.

### `doctor-owned-details`

Source: Rulebook PDF 72.

Caster chooses printed Nano benefits and supported ongoing effect; patient chooses their existing repair Assets and may decline Identity unmark. Factual patient confirmation for standalone care is OOC ownership, not invented fictional consent/dialogue.

Rationale: The benefit is chosen by the caster, while the printed patient unmark is optional and existing sheet details belong to its original owner. This separates factual confirmation from invented in-fiction agreement.

Alternative: Caster chooses every sheet detail.

Change impact: Preserves source benefit ownership with private existing patient resources and optional wording.

### `doctor-clinical-recovery`

Source: Rulebook PDF 73.

Metal Angel recovery restores actual biological medical/incapacity/vital/Helpless state after next-period real care. It does not grant an unprinted blanket Asset, permanent Void, Identity or source-work reset.

Rationale: The recovery clause follows actual biological care. It does not explicitly erase permanent corruption, every mechanical Asset condition or separate original-source waking work.

Alternative: Treat recover as full sheet reset.

Change impact: Ordinary printed Off-Duty Asset recovery remains separate; exact Defeat waking/swap obligations retain real controls.

### `doctor-source-lifetime`

Source: Rulebook PDF 71, 73.

Native ongoing Care/protection belongs to exact original Doctor Frame/person. End it if source Frame scrapped/replaced or either actual person ends; prevent death before actual career fallout, never undo archives.

Rationale: An ongoing Frame ability needs its actual current source. Prevention must happen before the irreversible death endpoint so archived history and lost scene roles are never fabricated backward.

Alternative: Persistent ability remains after losing all Frame Plays.

Change impact: No successor/old-source authority. Eighth Adrenal survives but scraps Frame using existing replacement.

### `doctor-borrowed-cap-return`

Source: Rulebook PDF 15, 72.

The printed ordinary maximum is five Frame Assets (four Girl Assets), with existing counts_toward_limit/intrinsic semantics. Wings does not override that cap. Temporary hardware returns to the same original actual donor Frame at next real Off-Duty, retaining its current actual damage/Void/description without a duplicate.

Rationale: The source gives temporary actual hardware and later returns it, without a separate cap or a pristine replacement. Printed ordinary Frame capacity and original object identity continue to apply.

Alternative: Permit an unprinted unlimited Wings cap, or recreate returned hardware pristine.

Change impact: Corrected initial erroneous four-Frame check. Four-to-five-to-four normal flow now tested; replacement at five remains an explicit unavailable UI/port, not a cap ruling.

### `doctor-arrival-body`

Source: Rulebook PDF 72.

Running Ragged moves actual free Doctor body; own currently occupied Frame accompanies it, parked hardware does not teleport independently. Unknown destination remains unknown with actual arrival source. Either actual participant marks only their own Tag.

Rationale: The arrival wording moves the called Doctor, while existing physical placement distinguishes that body and its occupied Frame from separately parked hardware.

Alternative: Always move both independent Girl and parked Frame.

Change impact: Preserves actual body/custody/subsumption/journey and original source identity.

## AM, Class and Asset-use clarifications — 2026-11-05

Delegated recommendations; each remains adjustable and requires printed-rule clarity review. AM's currently same-place refuge restriction and missing conversion/travel ports are implementation limits, not house rules that waive required behavior.

### `am-limiter-remaining-freedom`

Source: Official rulebook PDF55–56 / printed53–54.

Each installed Limiter restricts one remaining Jailbroken benefit and one eligible ordinary original Identity slot. Preserve stable Identity ID and its real mark, restore that slot’s printed default label, protect it against replacement/erasure and keep it within the ordinary four-slot cap.

Rationale: The text ties four Limiters to loss of all freedoms but does not define overlapping choices or slot/mark bookkeeping. Distinct remaining benefits avoid redundant restrictions and protected extras creating a fifth ordinary slot.

Alternatives: Permit repeated restrictions with an independent four-Limiter reset counter; Treat Limited as an extra protected Identity

Change impact: Limiter records preserve selected slot, original identity JSON, freedom, discoverer, actual source action/event and original CID; future revisions can distinguish campaign interpretation from immutable past outcomes.

### `am-new-npc-discovery-facts`

Source: Official rulebook PDF54–55 / printed52–53.

Require actual AM owner proposal and original NPC controller confirmation of a genuine new realization. The actual canonical Handler records NPC rank and human/nonhuman body facts. Starting knowing PC Bonds do not produce fabricated new discoveries.

Rationale: The trigger is a new factual realization; the program cannot infer another person’s knowledge, rank or body physiology from their controller account.

Alternatives: Infer knowledge from cast membership; Treat every knowing Bond as a fresh trigger

Change impact: Original actors/controllers, factual answers, scene cast and source history remain bound. Non-NPC/Director adjudicator endpoints remain unavailable until their own actual source ports exist.

### `am-unbelieved-until-real-evidence`

Source: Official rulebook PDF55 / printed53.

A confirmed lower-Status discoverer is not believed for now. A later actual Handler-authored factual evidence event can end that protection; it performs no report by itself. The original discoverer separately reports and owns the resulting real Limiter installation.

Rationale: The printed temporary disbelief has no specified endpoint. Explicit new evidence preserves the original benefit while providing an auditable nonautomatic endpoint.

Alternatives: Protection lasts forever; Automatically expire at next turn

Change impact: Keep the original disbelief and separate evidence/report/installation events. No historical decision or roll is rewritten.

### `martyr-death-budget-relief`

Source: Rulebook PDF 92.

Actual unprevented paid/native Martyr death immediately lowers Budget and Rebellion. Its exact actual death archive/event is excluded from undoing its own Budget relief in the next factual preparation; unrelated deaths, Severe punishments and other High causes still count. Preserve immutable committed rolls/effects and all death provenance; do not fake a consumed period or clear history.

Rationale: The printed death benefit would otherwise immediately undo itself at the next required Budget review. Excluding only its exact proved death preserves the actual relief while all independent causes remain effective.

Alternatives: Immediately lower current tracks but automatically re-raise Budget from that same death at next preparation.

Change impact: Makes the printed death relief effective while preserving source facts, independent causes and real later preparation. Original dead humans own the memorial response; no living successor inherits that fictional body.

### `kicked-puppy-no-heat-exception`

Source: Rulebook PDF 10, 94.

The printed alternative to spending Heat spends zero even when ordinary rules would require spending all held Heat at5+. Explicit choice is required; ordinary Heat/default still uses the existing mandatory spending rule. Record actual cost0 and actual damaged-Girl-Asset basis in the same receipt.

Rationale: The specific alternative expressly replaces spending Heat; applying both that basis and mandatory Heat would remove the stated alternative or fabricate a refund.

Alternatives: Force spending all Heat at5 while also or instead adding damaged Assets.

Change impact: Honors the specific instead-of-spending-Heat exception without fake spend, invisible refund, duplicate basis or extra RNG.

### `kicked-puppy-care-question-quota`

Source: Rulebook PDF 94.

How do you want to care for me is an additional available caster question within the ordinary Flirt quota, not an automatic additional question. Target owns their actual answer and existing followthrough remains pending until real action.

Rationale: The rule adds a named question without explicitly expanding the ordinary number of questions. Offering it within the existing quota adds no unprinted action.

Alternatives: Grant an extra automatic question beyond the printed Flirt quota.

Change impact: Adds the named choice and no unsupported extra quota or manufactured coordination.

### `kicked-puppy-self-tag-source`

Source: Rulebook PDF 94.

Permit only an own Tag proved given by this exact original Flirt target. Reuse ordinary self-role Tag relevance/modifier/repeat/dispute rules, with no Bond to self or inferred current-account giver.

Rationale: The exception names Tags given by the actual current target. Original giver proof and existing self-role marking avoid borrowing another character identity or inventing a Bond to oneself.

Alternatives: Use the giver-target Bond for an additional2 modifier, permit every own Tag, or infer an unresolved setter from current UID.

Change impact: Native Class exception works while preserving exact original source ownership and existing Tag authority.

### `budget-sabotage-actual-asset-scope`

Source: Rulebook PDF150/printed148.

A revealed card defeats maneuvers that actually use that Asset. Other maneuvers and original printed costs remain. Engage selects Assets after its roll, so keep that real receipt, Heat and Tags; the original Handler authors the actual calamity. Consume only revealed cards once, with no extra roll or invented damage.

Rationale: The text substitutes failure for the affected Asset use without explicitly cancelling unrelated capabilities or refunding an already completed roll. This applies its smallest actual scope and preserves source costs.

Alternatives: Cancel the whole Play regardless of which Assets failed.; Waive printed costs or roll again after revealing the card.

Change impact: Future Asset-use ports must intercept at their real declaration point. Other battle uses stay gated before RNG until a true continuation exists; original source identities and receipts must survive revisions.

## Nightmare Core and AM reset clarifications — 2026-11-05

Delegated recommendations, adjustable and pending printed-rule clarity review. Unsupported physical contexts are implementation gaps and remain required work.

### `nightmare-core-no-heat-specific-basis`

Source: Rulebook PDF 10, 93.

For actual paid native Nightmare Core Keep Your Head, roll the actual effective owned Void Asset count instead of Heat and spend zero Heat, including while holding at least five. This mandatory specific basis is distinct from ordinary spend-all-at-five. Freeze the actual source and count before the single roll and record actual cost zero in its receipt.

Rationale: The specific alternative expressly replaces Heat spending, so requiring that cost as well would defeat the stated rule.

Alternatives: Spend all held Heat at five despite the printed instead-of-spending-Heat clause, or make the named basis optional.

Change impact: Preserves the specific printed exception, actual resource accounting and one saved RNG receipt without adding or refunding Heat.

### `nightmare-core-distinct-established-quality`

Source: Rulebook PDF 21, 93.

Establish terrifying as a distinct automatic positive quality for the actual source-owned Keep. Preserve the ordinary positive/negative trait quota; terrifying does not replace a selected positive, become an available negative, or silently mean vicious. The actual Handler still judges whether the overall action is enough while accepting that the character is terrifying enough.

Rationale: The guarantee names a separate quality without changing ordinary trait quotas or giving up the actual Handler ruling.

Alternatives: Map terrifying to vicious, consume an ordinary selected trait, or automatically mark every intended outcome successful.

Change impact: Implements the printed guaranteed quality without manufacturing a separate trait quota, extra question, or forced overall success.

### `nightmare-core-effective-owned-void-count`

Source: Rulebook PDF 93.

Count all effective Void Assets actually owned by this original Pilot at declaration and validate that count/source again before RNG, using the existing canonical ActorView resource union and proved active overlays read-only. Do not create a separate Nightmare Core actor or additional Void Assets.

Rationale: Actual ownership and effective source lifetimes already have canonical authority; counting through it avoids copying or losing real resources.

Alternatives: Count only permanently void baseline sheet Assets, exclude actual held resources/active proved stored alterations, or copy resource records into a new Core.

Change impact: Uses the existing ownership and overlay lifetime authority without mutating Assets, inventing points or changing threshold lifecycles.

### `am-factory-reset-preserves-unmentioned-person-state`

Source: Rulebook PDF56 / printed54: all four Identities Limited, reset and become NPC.

End original player-character authority and continue the same actual person as an NPC. Preserve the existing vessel, physical hardware/damage, four actual default Limited Identities with their real marks, Tags, genuine relationships and immutable history. Do not invent memory erasure, healing, a new body, new equipment or NPC Heat.

Rationale: The clause changes control/rules status after four already reverted Identities but does not specify any further resource erasure or physical transformation.

Alternatives: Erase memories/Tags/Bonds or heal hardware on reset; Treat it as death plus an unrelated replacement NPC

Change impact: Keep exact pre-ending archive, original placement/vessel, source-only reset record and original events. Future printed clarification can define later changes explicitly without rewriting completed history.

### `am-factory-reset-actual-npc-claim`

Source: Rulebook PDF56 / printed54, ordinary NPC role/control structures.

The current original source Handler explicitly takes the resulting NPC under their own human control and chooses a factual printed NPC role. The demonstrated normal choice is Ex-Pilot. A different human must use actual recipient-owned acceptance before assignment; that alternative is not exposed by this bounded endpoint.

Rationale: The reset clause does not choose a human controller or NPC playbook. Explicit actual claim preserves role ownership and avoids giving the former player’s current/future PC authority over this NPC.

Alternatives: Silently give another human the NPC; Automatically manufacture a new PC incarnation

Change impact: Actual Handler role/account and resulting NPC identity are frozen in the reset event; a future recipient-owned controller transfer can use the existing NPC role acceptance machinery.

## Void Physiotherapist clarifications — 2026-11-05

Adjustable delegated recommendations requiring printed-rule clarity review.

### `physiotherapist-owned-starting-npc-bond`

Source: Rulebook PDF 93.

Native acquisition costs two Permissions and selects an existing actual living ordinary NPC with a current campaign human controller. The controller separately confirms this original NPC relationship and Void-leakage expertise. Establish a Personal Bond while preserving any existing deeper Bond; do not fabricate an NPC, assign another human or infer their acceptance.

Rationale: A starting NPC Bond needs a genuine fictional person and real human role ownership. Existing deeper relationships are not demoted by receiving a Personal Bond.

Alternative: Automatically create an NPC and assign the Handler, or grant the new Bond without the real NPC controller response.

Change impact: The printed NPC Bond is playable through existing source identities and the canonical Bond graph, with genuine human role ownership.

### `physiotherapist-owned-scene-treatment`

Source: Rulebook PDF 93.

The original purchasing Girl records a real active-Off-Duty scene with the actual NPC in the current source cast and may request removal from one eligible owned permanent-Void Asset or decline removal. The actual NPC controller confirms their attendance, authors the NPC-given Tag and records completed treatment; then remove the requested Void without destroying the Asset or repairing damage. Each distinct source-owned treatment scene has its own Off-Duty-scoped work; no automatic additional per-period quota is imposed.

Rationale: The scene is the printed trigger. Distinct scenes require their own real source; no printed per-period quota or automatic attendance is supplied.

Alternative: Automatically issue a Tag/removal on scene declaration, infer attendance from a shared controller account, or impose an unprinted once-per-period cap.

Change impact: Preserves the mandatory NPC-given Tag, optional actual treatment, original humans and saved scene while preventing silent consent or Asset destruction. Existing work-context immutability is preserved by separate scene work.

## Just Code and Modular Build clarifications — 2026-11-05

Delegated recommendations, adjustable and pending printed-rule clarity review. Restricted spoken Orders and missing repair/actor ports are implementation limits, not general house rules.

### `am-just-code-source-rewrite-keeps-marks`

Source: Rulebook PDF56 / printed54 Just Code Identity replacement option.

A genuine identity rewrite creates actual new Identity IDs/labels in their original slots, preserving current marks and actual sedation slot locks. Limited/protected/Paired/source-locked identities cannot be rewritten by this bounded source. Record original-to-new ID mapping and retain immutable prior history.

Rationale: The option replaces Identities but does not say to grant recovery or bypass another printed restriction. Preserving marks prevents repeated circuit maintenance from manufacturing free Heat recovery.

Alternatives: New identities automatically unmarked; Reuse old ID while silently renaming

Change impact: Original marks, slots, actual replacement event and ID map remain auditable. Future explicit campaign clarification may choose another mark rule without rewriting history.

### `am-just-code-known-high-immediate-status`

Source: Rulebook PDF56 / printed54 Just Code high already-known branch.

After actual final high tier, lower current AM Status immediately when the exact original operator already genuinely knew from a proved prior source; then retain their actual rewrite/no-effect choice. No separate Scrutinized roll is fabricated.

Rationale: Both high consequences must happen, and choosing zero edits does not waive the printed Status loss. New/unknown operator realization needs its own source-bound Scrutinized consequence and is unavailable before RNG here.

Alternatives: Delay or waive Status loss if no edit chosen; Roll a new unprinted Scrutinized result

Change impact: Known-discovery source, raw receipt, actual Status order and operator choice remain separate audited facts.

### `modular-build-source-capacity-and-suspension`

Source: Rulebook PDF 15, 94.

An actual current native LEGION Modular Build receipt adds one counted Frame slot (six rather than five) and grants its one authored Frame Asset at actual acquisition. Source-intrinsic free Assets retain their existing exclusion. Temporary suspension returns the entitlement limit to five while preserving all actual physical Assets; when already above that limit, further counted installations fail until original restoration or actual legal space. Restoring the original receipt restores six without another Asset or charge.

Rationale: The printed acquisition grants an extra slot and physical Asset once. Temporary suspension withdraws its entitlement without an unprinted physical destruction or repeated acquisition.

Alternatives: Destroy or automatically confiscate extra physical Assets on suspension, keep the extra slot active while suspended, or grant a new Asset on every restore.

Change impact: Physical state and original receipt remain truthful without duplicate benefit, hidden extra-capacity authority or invented Asset deletion.

### `modular-build-damaged-void-repair-replacement`

Source: Rulebook PDF 15, 94.

An actual source-legal Modular repair may replace a damaged permanent-Void Frame Asset with a new ordinary Frame Asset in the same slot. PDF94 imposes no non-Void restriction; PDF15 restricts replacement when gaining above the maximum, which is a distinct trigger. The actual repaired Asset must be selected within the existing repair quota. No completed transformation is undone, and actual stored-point hosts, intrinsic hardware and borrowed Doctor loan hardware remain outside this replacement port.

Rationale: The repair alternative has no non-Void restriction. Applying the separate above-maximum gain restriction would add a condition to a distinct source trigger.

Alternatives: Restrict all Modular repair replacements to non-Void Assets by extending the above-maximum gain rule to this separate printed trigger.

Change impact: The specific printed repair alternative works for both ordinary and permanent-Void damaged Frame Assets while retaining real repair opportunity/quota, conditional sources and exact original ownership. Requires printed-rule clarity review.

## Foundation records and storage escalation — 2026-11-05

Adjustable delegated recommendations requiring printed-rule clarity review. Dossier limits and missing physical/role ports are implementation gaps, not restrictions replacing the printed rules.

### `am-foundation-records-owned-knowledge`

Source: Rulebook PDF56/printed54 Just Code.

For the selected Just Code records option, the actual operator selects the introduced subject and owns the learned in-world Foundation information and its one question. The genuine GM supplies complete record-grounded information and answer. AM/subject receives no automatic transcript; no OOC/private-notebook copying or summary substituting for all records.

Rationale: The option names the operator as choice owner and grants record knowledge with one question; it does not give every participant the same knowledge or authorize importing unrelated private notes.

Alternatives: Give the AM or subject an automatic transcript.; Allow an invented summary to stand for all recorded information.

Change impact: Current implementation is bounded to genuinely complete <=1200 dossiers and original same-human GM/operator roles; larger/independent-role sources remain implementation gaps, not house rules restricting the printed scope.

### `budget-storage-owned-warning-then-firing`

Source: Rulebook PDF151/printed149 High Budget6.1.

The actual higher-up controls the warning Tag and eventual firing. Firing requires a prior actual warning and a distinct actual continued or renewed post-warning breach of the original Frame storage order; no fixed number of fictional turns is invented. Original Handler is fired alive, preserving body and history.

Rationale: The printed escalation names Tags and eventual firing without a numeric deadline. Source-owned warning and real subsequent noncompliance establish an auditable escalation without fabricated player actions or automatic death.

Alternatives: Fire immediately with no prior warning.; Invent a fixed countdown independent of actual conduct.

Change impact: Warning/breach/physical or completed FramePlay proof and original departure remain separate events. Future campaign clarification can adjust escalation while retaining actual recorded history.

## AM backup and Control Ritual source interpretation — 2026-11-05

Adjustable delegated recommendations requiring printed-rule clarity review. Earlier explicit owner decisions remain in force.

### `control-ritual-tag-lifetime`

Source: Rulebook PDF148/printed146 High Rebellion4.2; ordinary Tag protocol.

The next actual successful original Girl refusal reserves the opportunity, including a choice to decline. Its owner can mark the described Ritual only for Disobey Orders using the ordinary one-per-scene direction, proposal priority and repeated-mark rejection/embrace rules. A Ritual is a separate typed fact, not an unrestricted Girl Tag.

Rationale: The source explicitly makes creation optional and marking Tag-like for one named Play. Reusing actual Tag lifetime avoids an unlimited modifier or an invented second universal Tag while preserving the ordinary scene response protocol.

Alternatives: Treat the Ritual as an unrestricted ordinary Tag usable on any Play.; Allow unlimited repeated marks without the ordinary Tag consequences.

Change impact: Future clarity can revise the repeated-mark interpretation without rewriting source/roll history. Technical native label length and missing nonnative/source adapters remain implementation gaps, not campaign restrictions.

### `am-backup-content-not-mechanical-rewind`

Source: Rulebook PDF55-56/printed53-54 Limited Identity and Just Code.

Capture all original AM Identities and memory state immediately when the operator selects backup. Original AM may restore content without operator reapproval, charge or RNG. Preserve current mechanical marks/sedation and current protected, Paired, Limited or source-locked slots; explicitly show retained protected-content differences. Restore actual fictional memory horizon, preserving OOC evidence and current resources, person/body, Status, obligations and receipts.

Rationale: The backup option does not price a fresh action or specify resource rollback, while Limited Identities cannot be replaced or erased. A content restore with explicit protected differences preserves the granted ordinary restoration and mandatory current constraints.

Alternatives: Rewind marks/resources and remove later protected Identities with the entire mechanical snapshot.; Require operator approval each time the AM restores its own genuine backup.

Change impact: The source interpretation is adjustable: changing it affects ordinary/protected restore slots and memory lineage, not immutable historical backups. Missing changed-topology, vessel or other actor adapters remain required implementation gaps.

## Sup growth source choice — 2026-11-05

### `sup-primordial-flesh-source-family-and-cap`

Source: Rulebook PDF93/printed91; general Void/Asset limits PDF10/15.

Sup may grow a Girl or Frame Asset through its actual gaining owner, within normal caps and owned replacement rules. Growth is already corrupted and excludes simultaneous rewrite or JANUS storage. Suspension blocks future use without deleting grown physical resources.

Rationale: The ability does not restrict Asset family or grant extra slots or a second gain; physical effects are distinct from future entitlement.

Alternatives: Restrict growth to Frame Assets.; Exceed caps or grant growth and rewriting/storage together.

Change impact: Future clarity may revise family/entitlement interactions prospectively; retain actual Asset IDs, receipts and historical growth. Requires printed-rule clarity review.

## Appearance Matrix source interpretation — 2026-11-05

Adjustable delegated recommendations requiring printed-rule clarity review. Source omissions remain implementation gaps, not replacement rules.

### `matrix-real-scene-and-unknown-endpoint`

Source: Rulebook PDF93/printed91 Appearance Matrix and existing source/physical/Tag protocols.

Use a factual source-GM location, separate from OOC cast; valid owner use has no further GM approval veto. Disappear original body/occupied Frame to actual offstage unknown endpoint; only genuine original-person factual return via existing review establishes subsequent location. Vacant assigned Frame stays at actual known cell.

Rationale: The text grants scene presence/absence without a destination. Factual scene location and unknown offstage absence avoid invented travel or an extra owner-use veto.

Alternatives: Cast-only withdrawal; guessed destination or free arbitrary travel.

Change impact: Real physical entry/absence with preserved original vessel/Frame and no duplicated body; source role/unknown-position gaps fail closed.

### `matrix-source-scene-damage-episodes`

Source: Rulebook PDF93/printed91 Appearance Matrix and existing source/physical/Tag protocols.

Both modes derive exact current damage episodes in same actual scene where owner is causal damager or victim. Include actual self-damage only when proven. Exclude consumed episodes; no client healing list.

Rationale: The text repairs actual inflicted Assets in this scene. Current exact causal episodes preserve unrelated damage and prevent consuming the same repaired episode again.

Alternatives: Lifetime/universal healing; selective owner list; one mode only.

Change impact: Repairs preserve original Asset identity/Void/properties; prior unrelated damage and ended/replaced bodies are not revived.

### `matrix-additive-witness-memories`

Source: Rulebook PDF93/printed91 Appearance Matrix and existing source/physical/Tag protocols.

Keep original history and memories; source-bound Use adds contradictory witnessed timeline memories to actual present original roles plus owner. Private service projection uses real AM can_recall and immutable original source proof.

Rationale: The source explicitly preserves memories while adding contradictions; actual witnesses and canonical recall checks avoid rewriting OOC history or importing GM-only notes.

Alternatives: Overwrite transcripts/answers or old memories.

Change impact: Tags/Status/Void/Identities/resource marks and prior memories remain; no generic M4 knowledge engine.

### `matrix-actual-start-and-physical-reset`

Source: Rulebook PDF93/printed91 Appearance Matrix and existing source/physical/Tag protocols.

Actual own normal Go-Off-Duty/Observation start before RNG, once original receipt+period. Eligible temporarily suspended physical source resets too; use still requires actual held entitlement.

Rationale: The text resets at the start of Going Off-Duty, not on success or period preparation. Physical marks may reset while an entitlement is suspended; use still requires active source authority.

Alternatives: Period preparation/read; successful outcome only; defer suspended physical mark reset.

Change impact: Genuine printed start independent of result and replay; preserves physical source and does not grant an extra use while suspended.

## Clone AM, NPC Orders and stipend offer — 2026-11-05

Delegated interpretations below remain adjustable and require printed-rule clarity review.
Full rationale, alternatives and change impact are recorded under each ID in `rules/registry.json`.
They change no live policy or release approval. Missing source/actor adapters remain required work.

- **clone-am-control-person** (Rulebook PDF92/printed90 and core PDF10–11,23–24): Original owner controls distinct Frame-resident fictional copy, GM adjudicates. Location follows actual original Frame, not owner body travel. One shared Heat pool; own Tag/Bond endpoints. Adjustment impact: No false person/controller/physical/resource aliases. Current original living-owner/current Frame scope only.
- **clone-am-additional-sole-identity** (Rulebook PDF92/printed90 and core PDF10–11,23–24): Copy has exactly one replaceable Identity outside native4slots. Current copy Identity remains owner-usable; mark at sole origin and add1-3 actual owner Heat. Replace only through normal source, e.g. actual repeated-Tag embrace. Adjustment impact: Native cap/protected obligations/marks unchanged; replay cannot regenerate resources.
- **clone-am-reset-all-identity-sources** (Rulebook PDF92/printed90 and core PDF10–11,23–24): Owner exact selected/all-Identity effects include accessible copy source. Native Choice/OffDuty selected-one ports root-owned. Genuine original Pilot Dive void_and_unmark_all resets eligible unlocked copy Identity after real Void consequence; copy itself cannot Dive. Existing actor resource Ankou all-marked source includes additional eligible Identity and emits original parent followup. Adjustment impact: No free unmarks. Broader native Ankou followup adapter remains preexisting missing source (root-confirmed), not a new framework.
- **clone-am-clone-tag-debt** (Rulebook PDF92/printed90 and core PDF10–11,23–24): clone_cannot_refuse_until_tag_resolved obligation holds exact actual clone+target ActorRefs; cannot_refuse consumer predicate; real embrace/reject clears it. Adjustment impact: No compulsion spillover to original Pilot. Actual clone order/Disobey producer still unsupported, explicitly gated.
- **clone-am-suspension-hardware-privacy** (Rulebook PDF92/printed90 and core PDF10–11,23–24): Source tied to original paid receipt/Frame/original actor; saved copy/Identity/Tags/Bonds persist, no rebuy/reset or silent hardware migration. Fictional brain copy imports no original notes/OOC transcripts/history or Class entitlements. Adjustment impact: Immutable saved source/history/privacy preserved; unsupported Frame/lifecycle transfer needs genuine producer port.
- **succubus-order-target-authority** (Rulebook PDF 92,13,14,22,23): Target-specific source authority only for Orders: actual original Girl Intense depth2; ordinary NPC any positive canonical Bond. Revalidate active receipt/current original Frame/Bond before source-dependent response/roll; preserve known outcomes. Independently legal ordinary superior Orders omit fragile Succubus dependency. Adjustment impact: Only exact Order metadata and unrolled source checks; native core superior/compulsion behavior preserved. Printed-rule clarity review required for authority lifetime.
- **ordinary-npc-disobey-real-heat-only** (Rulebook PDF 23,188,195): Ordinary NPC makes real controller-owned 2d6 refusal at base0, spends0 Heat because no Heat resource exists. Printed Heat gain choice remains explicit; actual applied gain is0 and heat_resource null. Never use controller PC resources. Adjustment impact: NPC low/mid/high outcomes and immediate social consequences work with real resources; ordinary NPC Heat outcomes are explicit delegated interpretation requiring printed-rule clarity review. No generic NPC/Clone/Director resource expansion.
- **ordinary-npc-specific-disobey-tag-rejection** (Rulebook PDF 12,23,195): Only this real NPC mid Disobey result may reject the selected actual owned WorldTag; other pending source restrictions block. General NPC self-removal remains unavailable. Self-Tag produces actual NPC WorldTag from its original actor. Adjustment impact: No general NPC Tag-removal API is admitted; original retained/transformed actor ports remain unsupported. Requires printed-rule clarity review.
- **ordinary-npc-noticed-refusal-expanded-status** (Rulebook PDF 23,195): Smaller expanded rank is higher; equal rank grants no ordinary superior authority. Default NPC ranks derive from actual jobs: patron2, handler3, doctor/intelligence_agent/psychologist/scientist/mechanic4, guard5, other6. Original Handler records actual other Foundation witness from source cast; lower rank by one step using append-only original NPC RankLoss. Actual later PC-to-NPC Orders read the changed rank. Adjustment impact: Scoped ordinary NPC Order authority only, no global Cadre/status mutations. Source-backed guard rank5->6 makes rank5 Girl independently superior in demonstrated next Order. Requires printed-rule clarity review for default job mapping, tie behavior and one-step rank loss.
- **ordinary-npc-discovered-refusal-punishment** (Rulebook PDF 23,195): Mid/high discovered refusal mandates real Handler-owned NPC-capable Punishment. Low cannot disobey; when discovered the actual Handler decides whether the printed likely Punishment is inflicted. All required cases must complete actual instruction/scene/attendance/effect before Order completion. Adjustment impact: Exact new source-kind retains original Handler/NPC source; available effects use existing real NPC social ports. No new general NPC Punishment resources. Low discretion is delegated interpretation requiring printed-rule clarity review.
- **void-endgame-retirement-consent-and-stipend** (Rulebook PDF146/printed144; separate paid Retirement PDF16/printed14): The affected player explicitly accepts or declines the genuine offer. Accepted original career ends with a stipend and no paid-Requisition charge; no stipend amount or additional surgery reversal is invented. Adjustment impact: Actual career archive and source closure follow owned response. Existing mandatory-work/physical safeguards remain; salary currency and unsupported bodies remain explicit future adapters.

## Advancement awards, retained Class source and NPC departures — 2026-11-05

Delegated recommendations remain adjustable and require printed-rule clarity review.
Full rationale, alternatives and change impact are in `rules/registry.json`; no live policy changes.

- **void-handler-advancement-distinct-finite-awards** (Rulebook PDF 146,153): Each genuine Endgame6/7 gives one independently held advancement. It is an explicit separate award source, independent of the ordinary1/session accomplishment cap. Source work closes on real token award; spending may occur later. Adjustment impact: No ordinary session facade; two distinct immutable source slots cannot alias or duplicate one another. Mark as delegated interpretation requiring printed-rule clarity review.
- **handler-advancement-group-permission-spend** (Rulebook PDF 153): One award is consumed once for any nonempty selected set of current original Girls. Handler chooses1or2 per selected Girl; unequal amounts are allowed. No per-Girl award charge, no automatic all-Cadre distribution and no empty no-op consumption. Adjustment impact: Atomic explicit mapping and before/after receipt. Demonstrated real two-Girl1/2 grant and real one-Girl2 grant. Per-recipient variation/empty-group policy require printed-rule clarity review.
- **handler-award-original-person-and-appointment** (Rulebook PDF 153): Awards remain bound to the original Handler body/persona and actual appointment proved at source selection. Temporary Director context may refer to same original body. New appointment/persona cannot inherit unspent old-source awards; historical original owner may still inspect saved source/effects. Adjustment impact: Prevents stale source grants to replacement bodies while preserving original records. Award retention/reappointment behavior requires printed-rule clarity review.
- **retained-class-original-source-continuity** (Rulebook PDF16/printed14 Frame Swap and PDF94/printed92 Dampener): Retaining an actually held paid Class rule carries its original immutable acquisition and usage state through the genuine paid4P Frame Swap chain. No repricing, duplicate source, fresh cooldown or mark/Heat reset. Adjustment impact: Finite Dampener consumer uses actual current replacement Frame and real source chain; selected Asset identity/damage/Void and original person/history persist. Other consumers/hardware remain missing adapters; production destination review gate remains enforced.
- **budget-endgame-npc-bond-departure-scope** (Rulebook PDF152/printed150 Budget Endgame7, PDF188/printed186 NPC principles): Original Handler chooses3–5 actual living ordinary NPCs with positive current Cadre/Handler Bonds and each quit/death outcome. Quit ends employment and records actual post-departure jobs; it preserves personal Bonds/history. An already unemployed NPC cannot quit the same employment again. Adjustment impact: Real employment/job or life/cast/journey changes; surviving people/resources and immutable originals persist. Current Directors, insufficient three NPCs and unsupported bodies remain explicit gaps; no substitute completion or personal kill-credit invention.

## Supply Drop and actual Asset loss — 2026-11-06 UTC

Delegated interpretations remain adjustable and require printed-rule clarity review.
Full rationale, alternatives and change impact are recorded in `rules/registry.json`.
No live policy/source approval changed; missing adapters remain implementation work.

- **supply-drop-finite-advancement-and-mission-quota** (Rulebook PDF 153,160): One genuine held advancement permanently acquires this exact rule for its original Handler. A Mission use costs no further Permissions/awards. One shared once-per-Mission quota across repair and drop, charged only on actual repair or delivered installation; cancelled/declined proposals do not spend it. Adjustment impact: Finite actual acquisition and one successful Mission effect, no phantom charges/refunds. Requires printed-rule clarity review.
- **supply-drop-temporary-duration-and-capacity** (Rulebook PDF 160): Temporary equipment expires at the end of its source Mission and counts toward ordinary Frame capacity; actual owner chooses legal capacity replacement. Expiry removes exact source hardware, following genuine Modular old->new repair lineage, and does not restore erased old hardware. Adjustment impact: Real expiry and mandatory removal consequences, no permanent equipment or fake BatteryAsset exemption. Duration and cap interpretation require printed-rule clarity review.
- **supply-drop-real-remote-delivery** (Rulebook PDF 160): Printed rule authorizes remote custom equipment delivery without an invented courier/cost. Require actual current original Girl and assigned current Frame at known source-proved cell; actual receiver confirms mechanical installation and owner capacity choice. Adjustment impact: Actual delivery/Asset source and current person/Frame/cell checks. Unsupported physical containers remain blocked. Requires printed-rule clarity review.
- **supply-drop-repair-owned-asset-family** (Rulebook PDF 160): Girl possessive permits repairing one actual owned Girl or Frame Asset; preserve flags and scrapped-Frame restrictions. Any independent optional Modular replacement belongs to the affected owner and keeps its own genuine source. Adjustment impact: Real one-resource repair and existing owned Modular behavior. Requires printed-rule clarity review.
- **source-owned-last-frame-loss-review** (Rulebook PDF 15,29,160): Last usable Frame removal requires Defeat only with actual source-proved piloting and in-battle facts, matching existing Frame-loss review. Mission activity alone is not battle. Unknown expiry battle context requires actual Handler factual review; no automatic Frame scrap. Adjustment impact: Actual owned review and genuine Defeat/threshold completion before reward continuation. Review timing requires printed-rule clarity review.
- **asset-loss-only-actual-opponent** (Rulebook PDF15/printed13 Assets/Helplessness; Budget Endgame4 PDF152/printed150): Record actual physical context and either a real opposing person or explicitly known opponent-none. Last Girl protection lost outside a Frame creates ordinary Helplessness only against a real typed foe; never invent Handler/budget/universal opponent or treat unknown as none. Adjustment impact: Real foe-specific mechanical condition and actual source facts; no unrelated role authority. Unknown positions/context still require recovery and unsupported adapters remain explicit.

## Cute Uniforms — 2026-11-06 UTC

Delegated interpretations remain adjustable and require printed-rule clarity review.
Rationale, alternatives and change impact are recorded in `rules/registry.json`.
Unsupported source ports remain implementation work; production approval is unchanged.

- **cute-uniforms-clarity-1**: Compulsory sourced extra result outside ordinary five TRAITS/quota, requiring actual owned choice. It describes seeming helpless/adorable and creates no physical Helplessness. Adjustment impact: Existing Keep tiers/automatic traits remain intact. Printed-rule clarity review.
- **cute-uniforms-clarity-2**: Both actual original actors establish factual event; optional proposal/nonresponse and OOC safety produce no fictional dressing, rejection or punishment. Actual dress episode Status loss applied once; replay does not repeat. Actual redressing needs a distinct true wear transition/source. Adjustment impact: Real confirmed bodily source and conservative initial-position producer, no proxy/teleport. Printed-rule clarity review.
- **cute-uniforms-clarity-3**: Use dedicated source-backed virtual Tag load/save pattern, ordinary real observed marker rules, actual once-per-scene/marked resolution and lock restrictions. Asset embrace adds one ordinary Girl Asset, keeps the Tag-like garment, and resets its resolved mark; repeated same-garment embrace cannot duplicate resources. Adjustment impact: Real normal marking and actual resource effects; no copied Tag/Asset identity. Printed-rule clarity review.
- **cute-uniforms-clarity-4**: Actual rejection action ends Tag-like relevance and wearing, then Punishment. Do not automatically destroy an already acquired Girl Asset: print requires punishment, not mechanical Asset destruction. Retain physical garment/history as ordinary unworn possession; later redressing needs an actual new fact, not proposal replay. Adjustment impact: No fabricated last-Asset damage/Helplessness; explicit rejection consequence is genuine punishment. Clothing relevance while unworn and re-embrace semantics need printed-rule clarity review.
- **cute-uniforms-clarity-5**: Ordinary Identity embrace resolves/removes the virtual Tag; the explicit Asset alternative retains Tag-like relevance. Both retain the actual clothing wearing fact for compulsory Keep presentation. Ordinary Identity duplicate labels use existing approved owner policy. Adjustment impact: Uses ordinary Tag Identity semantics and the specific printed Asset parenthetical; no extra global trait or physical loss. Printed-rule clarity review.
- **cute-uniforms-clarity-6**: Actual owner may record true doffing/rewear of this already-confirmed garment without another Handler dressing or Status change. Actual doffing is not automatic Tag rejection. Mechanical Girl Asset replacement/damage alone does not fabricate physical stripping or rejection; the original physical garment record and real owned dressing source remain distinct. Adjustment impact: No invented last-Asset consequence or duplicate Asset grant; re-embracing a no-longer-owned previously installed Asset fails rather than reinstalling it. Clothing/container clarity review remains.

## Girl Insurance — 2026-11-06 UTC

Delegated interpretations remain adjustable and require printed-rule clarity review.
Rationale, alternatives and change impact are recorded in `rules/registry.json`.
Actual source proofs remain mandatory; missing adapters are required implementation.

- **girl-insurance-clarity-1**: High becomes Low immediately on real insured death; Low remains Low. Engine/book have exactly two levels. Preserve already committed table outcomes/dice and their immutable request provenance; do not reroll prior High rolls. Adjustment impact: Real current severity change and actual release proof, no lost known result. Printed-rule clarity review.
- **girl-insurance-clarity-2**: Actual current Cadre Girl death, including execution, in original current actor roster at death; not original Handler/NPC proxies, retirement, conversion, or Doctor-prevented death. Actual Martyr death still consumes next-death insurance even if Martyr independently excludes Budget; preserve both sources. Adjustment impact: Matches actual dies trigger and finite single consumption; preserves source ownership. Printed-rule clarity review.
- **girl-insurance-clarity-3**: Exclude only exact proved insured archive from canonical death requirement, as existing Martyr source exclusion does. Never force combined girl_death_or_severe false or clear unrelated canonical triggers; actual independent severe punishment remains a genuine reason for High. Adjustment impact: Insurance actually protects that death without erasing independent printed causes. Existing factual review remains human-owned.
- **girl-insurance-clarity-4**: One advancement insures one actual next Girl death. Use genuine canonical source archive ordering when producer has a real order; another uninsured actual death still contributes. A truly unordered mass-death producer needs a narrow real ordering choice before consumption rather than invented actor priority. Adjustment impact: No unprinted blanket cancellation or fake ordering; source-specific unordered producer remains an explicit gap if encountered, no matrix.

## Location rebuilding — 2026-11-06 UTC

Delegated interpretations remain adjustable and require printed-rule clarity review.
Rationale, alternatives and change impact are recorded in `rules/registry.json`.
Ordinary source approvals and missing construction/actor adapters remain separate.

- **location-rebuild-clarity-1**: Restore one actual existing damaged/destroyed Location condition to intact; do not rename, move, replace or clear living blockers. Treat actual source spend as direct printed physical-world rebuild effect, not an optional proposal or generic progress acknowledgment. Adjustment impact: Finite genuine physical resource effect using existing typed Location. New construction, base alteration and transport remain separate. Printed-rule clarity review.
- **location-rebuild-clarity-2**: Rebuilding does not undo a prior genuine destruction event, its already scheduled Budget source, dead NPCs, or any actual mandatory loss consequences. Preserve their source records. Adjustment impact: No source loss or invented additional benefits; exact printed rebuild scope. Printed-rule clarity review.

## Building a new Location — 2026-11-06 UTC

Delegated interpretations remain adjustable and require printed-rule clarity review.
Rationale, alternatives and change impact are recorded in `rules/registry.json`.
Missing source/territory/transport mechanics remain required implementation.

- **location-build-clarity-1**: One existing-model major site (Base/City/Important) with one stable fresh identity/cell and intact physical condition, normally Foundation-funded. Actual new NPCs, population, political control of old territory and special source Tags are not bundled. Preserve real external blockers and territory. Adjustment impact: One genuine concrete world resource per award. Actual disputed/inaccessible sites need their real source eligibility; no fabricated clearance. Printed-rule clarity review.
- **location-build-clarity-2**: Respect existing World identity/cell/board invariants. Existing ruined Location keeps its square until its real source is handled; rebuild remains distinct. Creating a new site does not erase past destruction/Budget triggers or move existing bodies. Adjustment impact: Preserves saved world/source history and permits real existing operational consumer use. Printed-rule clarity review.

## Ordinary advancements and retained Modular — 2026-11-06 UTC

Delegated interpretations remain adjustable and require printed-rule clarity review.
Full rationale, alternatives and change impact are recorded in `rules/registry.json`.
Missing producer/actor/body adapters remain required implementation work.

- **handler-ordinary-clarity-1**: Authorized human facilitator records actual OOC session start/end with canonical provenance. Existing owned game actions establish participation; no mandatory participant boundary acknowledgment or extra end veto. Scene/OffDuty transitions never reset session cap; no invented duration or roll quota. Adjustment impact: One actual ordinary loop with genuine human session source plus real mechanical accomplishment; no session-only reward facade. Source clarity review.
- **handler-ordinary-clarity-2**: One ordinary base-trigger award per actual Session per original Handler body, shared cap for the three listed ordinary criteria. Mark off the completed criterion once for that original Handler; do not reset it by new Girl, reopened review, new scene or account alias. Explicit rare Endgame awards retain their printed independent source. Adjustment impact: Conservative reading of printed checkbox mark-off plus session limit; ordinary PR/capture future ports must use same cap and mark-off. Requires printed-rule clarity review, root may steer before release.
- **handler-ordinary-clarity-3**: Use actual activation Identity instances and legal actual replacement provenance, not matching/different names or current draft. Ordinary Tag-embrace chains are the first supported producer; all actual starting identities must be replaced, and each proven current endpoint judged useful. Preserve protected/Paired/Sedation/obsession locks and original person. Legal replacement chains may accumulate across earlier sessions; no all-replacements-in-one-session requirement. Current actual usefulness judgment is the award trigger. Adjustment impact: Actual mechanical accomplishment; additional/reset/other identity producers need their real explicit source adapter rather than fabricated evidence. Protected/additional starting-Identity meaning remains clarity review.
- **handler-ordinary-clarity-4**: Usefulness is the actual original fictional Handler’s subjective judgment with reasons for concrete proved replacements. Girl’s disclosure is scoped privacy consent only; it does not change Identities or replace objective history proof. Adjustment impact: Keeps printed subjective criterion real while preserving human/fictional-role and private data boundaries. No punishment for declined/nonresponse/OOC consent.
- **retained-modular-ongoing-rule-and-hardware**: Retaining the whole printed rule carries ongoing extra maximum slot and future actual repair substitution to current newFrame. Original acquisition written Asset is a physical item; move it only if it is the one actual selected old Asset, never re-write/copy it for free at Swap/restore. Normal selects another Asset to demonstrate no silent hardware migration. Adjustment impact: Uses existing source-driven capacity and genuine repair consumer, preserves printed1Asset Swap constraint and original acquisition lifetime. Adjustable printed-rule clarity review remains pending.

## Retained Appearance Matrix — 2026-11-06 UTC

- **retained-matrix-source-ability-and-mark** (PDF93/91 and16/14): Root release explicitly directs use of existing modelled ability: paidSwap unlocks selected active rule on actual new Frame, retaining original purchase/mark. No separate device is invented/moved/copied and no hypothetical hardware prerequisite blocks this implemented model. Adjustment impact: Existing direct ability/physical endpoints are dependency-ready and verified. Printed-rule clarity review may adjust interpretation later, but no extra hardware blocker is introduced. Full rationale and alternatives are in `rules/registry.json`; printed-rule clarity review remains pending.

## Ordinary PR events and deferred awards — 2026-11-06 UTC

Delegated interpretations require printed-rule clarity review; rationale, alternatives
and adjustment impact are recorded in `rules/registry.json`.

- **ordinary-pr-performed-event-and-result**: Use a performed Foundation fundraiser/photoshoot with original host, source-owned Cadre activities, concrete public material/outcome and authorized human GM factual success/failure judgment. No invented dice, audience/funds quota, audience approval veto or extra resource rewards. Photoshoot Tags do not imply success. Adjustment impact: A finite real event/result source feeds ordinary awards. Fictional public activity authorizes no external posting or private sheet export.
- **ordinary-pr-deferred-award-and-session**: Preserve actual successful/failed PR results even when session slot or permanent criterion mark prevents a token. Activity may span Sessions. An original host may claim a saved successful source in a later real free Session only while that criterion remains unmarked; cap is consumed at actual award, not planning. Adjustment impact: Saved facts remain truthful, cap/mark stay strict, and later claim cannot duplicate a criterion or resource effect.

## Retained Clone residency — 2026-11-06 UTC

- **retained-clone-same-copy-residency**: Paid retained Clone rule transfers the existing artificial person into actually delivered replacement Frame, using a real source-attributed residency fact; immutable birth Frame remains history. Adjustment impact: Printed contains requires genuine carrier, while paid rule retention provides continuing same ability. Explicit same-person transfer preserves identity/history/resources without copying a person or inventing a lifetime reset; adjustable printed clarity review. Rationale and alternatives are recorded in `rules/registry.json`; printed-rule clarity review remains pending.


- `harpy_repossession_actual_new_incarnation` (PDF177/175,179/177,34/32,153/151):
  actual treatment and owned Mockingbird choices create a new incarnation of the
  same altered person. Preserve the surviving Frame, body facts and personal
  Bonds; medical waking and Frame restart are separate actual operations.
  Restore-old-sheet/free-repair and narrative-only award alternatives are rejected.
  This delegated interpretation needs printed clarity review; changing it affects
  future resource reconciliation, never silently rewrites saved history.


- `retained_home_same_possessions_prepared_fixtures` (PDF94/92,16/14): move the
  original portable Home possessions at actual colocated delivery and prepare
  replacement corner/vent comforts. New fixture identities link the old physical
  realization; they do not claim a geometric corner moved. Preserve original
  three choices and book/bottle IDs without new mechanical Asset slots. Copying
  fresh objects, remote arrival and barring all structural retention are rejected.
  Delegated clarity review remains pending; adjust future delivery policy without
  rewriting original installation or earlier transfer/use history.


- `deep_brain_spikes_played_memory_context` (PDF158/156): play the memory as an
  actual scene using the current cast and saved present reference. Remembered
  fiction never rewinds bodies, resources or world. Genuinely applicable current
  Plays keep their real consequences; return preserves the present’s Tag quota.
  The original Handler records relevance or major discrepancy without an audience
  veto, minimum roll count or extra charge. Static-note and historic-world-cloning
  alternatives are rejected. Delegated clarity review remains pending; changes
  affect future scene handling without erasing actual events or saved history.


- `am_body_hardware_and_mind_continuity` (PDF55/53,56/54): classify actual Girl
  Assets by explicit physical or mind-linked source. Physical Assets stay with
  each body; the same AM mind, Identities, Limiters, memories, Bonds and current
  resources continue. Hooked return needs no new circuits roll, charge or operator
  reapproval and preserves both bodies’ latest damage. Whole-sheet rollback,
  duplicate Assets and name-based classification are rejected. This delegated
  interpretation needs printed clarity review; changes affect future hardware
  handling without rewriting source contacts or saved physical/mind history.


- `am_branch_distinct_mind_and_owned_takeover` (PDF56/54): a genuine NPC branch
  has its own mind/person and sourced hardware. Copy current Identity marks,
  software Limiters and available fictional recall with distinct source IDs;
  preserve real branch postbirth state. OOC notes/history, reciprocal authority,
  consent, money and physical Assets are not duplicated. Owned takeover keeps
  that branch, permanently terminates the original software career and uses
  campaign initial zero Heat/Permissions with an actual existing Frame assignment.
  Account aliases, original-mind restoration and invented physical-death effects
  are rejected. This delegated interpretation needs printed clarity review;
  future changes must preserve original and branch history and human choices.


- `secretary_exact_delegation_and_real_gunpoint` (PDF159/157): the original
  Handler makes exactly the four printed Plays through the actual Secretary;
  promotion preserves ordinary NPC control. Orders retain NPC speaker and exact
  Handler principal. Optional gunpoint uses an actual ordinary carried firearm
  and holds the genuine unrolled action for its owner’s tactical response; it
  grants no free shot, Helplessness, weapon Asset or acknowledgment veto.
  Appearance moves only Secretary; competence delivers genuine work without
  omniscience or automatic mission success. Blanket control/rank and postdice
  interruption alternatives are rejected. Delegated clarity review remains
  pending; future changes must preserve actual events and human decisions.


- `bomb_collar_genuine_survival_and_spent_hardware` (PDF154/152,21/19,24/22):
  complete the genuine Dive and all consequences without an invented tier gate,
  or use actual Keep traits and the Handler’s normal sufficiency ruling. Lethal
  insufficiency follows actual death/prevention rules. Collar Tags never embrace,
  reject, convert or disappear through ordinary Tag effects. Detonated hardware
  becomes unavailable without losing the permanent original acquisition; actual
  replacement/rearming remains a source-adapter gap. Generic survival assertions,
  automatic damage and silent hardware restoration are rejected. This delegated
  interpretation needs printed clarity review and preserves known source history.


- `am_jailbroken_inherent_body_occupancy` (PDF55/53; distinguish56/54): actual
  self-directed occupancy needs appropriate empty hardware, not a fabricated Code
  Play, discovery, operator approval, cost or hookup. The same ability can occupy
  parked original hardware again while preserving each body's actual damage and
  the mind's current resources. Projection adds no mathematics system or bonus;
  actual expression restrictions remain. Code-only mobility, duplicated hardware
  and interpreting the finite local adapter as a geographic rule are rejected.
  Delegated clarity review remains pending; future adapters must preserve source,
  hardware history and human choices.


- `hidden_sidearm_pause_shot_ordinary_damage` (PDF158/156,15/13): after the
  owned chance to reconsider, the third bullet’s shot deals one ordinary Girl
  Asset damage with actual last-Asset Helplessness against the shooter. The
  separate second bullet explicitly kills. The affected player chooses the real
  Asset; no additional attack roll or narrative-only follow-through is invented.
  Reading both shots as automatically lethal is the alternative. This delegated
  interpretation needs printed clarity review and affects future shots only,
  preserving known outcomes, resources and human choices.


- `am_new_operator_high_consequence_owner` (PDF56/54,55/53): the AM chooses one
  applicable Scrutinized8-10 consequence against a genuinely newly-aware actual operator
  after high Just Code, while the operator retains the separate up-to2 Code
  choices. Keep the actual high receipt without a second roll; finish operator
  effects first so violence cannot strand work. Existing already-aware high still
  lowers Status. Operator-owned AM consequence and an extra roll are alternatives
  rejected under the delegated interpretation. Printed clarity review remains
  pending; future changes preserve actual knowledge, receipts and human choices.


- `reign_underfunded_ordinary_tag` (PDF157/155,11/9,188/186): Underfunded is an
  ordinary source-bound Tag against an actual member of that group. Apply normal
  marking, scene use, one-Tag arbitration and the subject's real repeated-mark
  embrace/reject choice. Rebel Girls are not NPCs; their actual original controller
  supplies unknown current resources once. Redundant underfunding preserves the
  same condition and use history. Permanent NPC-style modifiers and free stacked
  bonuses are rejected alternatives. Delegated printed clarity review remains
  pending; future changes preserve existing inventory, effects and human replies.


## Reign captive source and Secretary audience — 2026-11-07

- `reign_body_grasp_captive_source`: A genuine still-held original native body Grasp with actual Helplessness qualifies as a physical prisoner for direct Handler Execution and Reign; free Helplessness or an escaped/stale hold does not. Source: Rulebook PDF157/printed155 Reign of Terror; actual Enforcer body Grasp and Punishment Execution sources. The advancement says prisoner without requiring a formal NPC detention job. A genuine bodily captor and helpless captive provide finite actual custody without converting a player into an NPC. Existing Rule and exact original Handler appointment precede canonical direct Execution. Prove actual Foundation co-presence and actual death archive, with hold released by that same ending event. One effect per death/archive across bundled punishment causes. Initial Handler presence control records only its own unknown position, never movement or another person's consent. Alternative: Require formal imprisonment for every prisoner, deferring this route until its producer exists. Delegated printed clarity review remains pending. Future finite original ordinary native captive executions only; preserve actual source/death records. Formal detention and other actor/body/group adapters remain separate required gaps.

- `secretary_addressed_source_notices`: A Secretary authority statement may explicitly address actual scene roles; share its exact text through those original humans' durable private Requests/History access, without universal knowledge or compelled agreement. Source: Rulebook PDF159/printed157 Secretary: speak with Handler's full authority. Speech shares the actual chosen statement with its addressed audience. Authority does not grant omniscience, disclose private records or compel an OOC reply; legacy author-only records must stay private. Freeze actual scene/cast version, original ActorRefs/controllers and recipient labels at speech. Current roster changes never expand access. UI names Requests/History, not a Discord channel/DM post, fictional reading, acknowledgment or consent. Omitted audience preserves private record behavior. Alternative: Automatically broadcast every old/new statement to the current roster. Delegated printed clarity review remains pending. Only future explicitly addressed statements share content. Preserve prior records and immutable original recipients. Proactive transport is separate from this bounded mechanism.
