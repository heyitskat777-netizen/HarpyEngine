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
