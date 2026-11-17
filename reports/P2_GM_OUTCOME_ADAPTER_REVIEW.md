# Which existing Plays need GM outcome adapters?

Reviewed source: `336ec6f8f09a00a4dfe5dbdad79e9b48a50bb19e`.
This is an implementation-side architecture review of all **63 catalogued native
entry points**, the separate diceless AM path, source wrappers and remaining
registered Play headings. It is not new printed-rule certification or another
gameplay test run. The registry remains RULES_SUBSET. No runtime behavior,
spending, deployment, release approval or player authority changes here.

## Finding

Do not build 63 generic GM success/failure adapters. The existing engine already
owns most printed outcomes and original human choices. The missing layer is a
small set of typed, source-bound GM interpretation/answer/world proposals, attached
only to the stage that actually needs them.

The previous phrase “five structured outcome adapters” needs precision:
**only ordinary Pilot Keep Your Head currently accepts a contextual GM ruling**.
Its proposal assesses whether the actual traits meet the goal, then its original
Handler choice owner confirms. For the other four ordinary Plays, the v2 protocol
accepts only `native_outcome` or `pending_choices` and rejects discretionary
assessments. Those four are source/readback adapters, not general GM judgments.
See [the actual validator](../src/girlframe/ai/gm_protocol.py#L108) and
[native source restrictions](../src/girlframe/services/director_native.py#L48).
The wider review queue also applies no outcome by itself.

Across the 63 native entry points:

| Recommendation | Count | Meaning |
|---|---:|---|
| GM interpretation/answer/world adapter required for the identified semantic stage | 13 | Includes the one ordinary Keep consumer already present; 12 other entry points need typed bindings, reusable across families |
| Conditional GM fact/consequence adapter | 17 | Only when the specified branch has an unresolved judgment; reuse a shared adapter rather than adding a second verdict to the whole Play |
| Native outcome/owner choices; no separate GM outcome adapter | 22 | Preserve the printed result and actual participants' decisions; a real child Play inherits its own needs |
| Handler, role or table content; no separate GM outcome adapter | 11 | A content/knowledge/coordination adapter may be useful, but it must retain the original authors |

“Required” means required to provide that **AI-assisted GM semantic step** safely.
It does not mean the existing human-native Play is broken or needs another roll.
“Conditional” is not permission for a model to invent a judgment requirement:
first use engine facts and the actual native pending source. Ordinary source
validation, privacy checks and outcome readback still apply in every category.

## Four shared GM adapter families

1. **Contextual goal ruling.** Keep Your Head: original goal, all demands, actual
   selected/automatic are/are-not traits, prerequisites and context. Keep the
   existing enough/not-enough/clarification contract. Extend source proof for
   genuine child, learned and alternate-actor uses instead of treating them as
   ordinary Pilot actions. Harpy `beautiful`, actual Handler/Harpy roles, and
   modified trait sets must come from the native source; no guessed trait mapping.
   The current ordinary-Pilot adapter explicitly rejects those broader sources.
2. **Evidence-bound answers and factual interpretation.** Start with Check Sensors.
   Bind each actual chosen question to canonical evidence and its legal disclosure
   scope, including uncertainty and original-owner confirmation. Add narrow
   variants for Snoop's proposed object existence/access, actual rank/body/Core
   facts and later proven poor-advice outcomes. Existing canonical facts should
   not require a model call. A GM must not answer a PC-owned private question on
   that PC's behalf.
3. **Combat admissibility and consequences.** Engage, All Out Assault, Go For the
   Core and Gorgon Attack share actor/target, original adjudicator, source Asset,
   opening/reach, actual vulnerability/defense and legal consequence evidence.
   Propose only the permitted fact/interpretation or consequence at that stage.
   Gorgon's existing `contest_judge` and `attack_judge` are concrete missing GM
   consumers: judge the actual pitted Assets or the permitted lands/averted result,
   respecting the unavoidable flag and any actual saving-Play outcome.
   Preserve native maneuver counts, damage, decisive results, target counters
   and all actual table votes. A GM proposal cannot supply unanimous advantage
   votes or turn a fixed native result into a discretionary failure.
4. **Bounded world outcomes.** Handler escalation/support/Contaminant Warp, Gorgon
   Collateral/Warp, PANDORA and Wraith AM need concrete entity/location/trait/
   consequence specifications. Bind them to the real grant, tier and source; use
   allowlisted native effects and real world consumers. Proposed text must not
   silently create an arbitrary NPC, object, mutation, ability or destroyed site.
   Original source owners still confirm their decisions.

These are shared protocols with distinct typed consumers, not one arbitrary
`effects` channel. The current empty-effect GMProposal cannot safely carry all
of these new operations without those consumers. A routing note is not one.

## Ownership and knowledge boundaries

- Printed “Handler chooses/answers” identifies a native decision owner. It does
  not prove that the fictional Handler is omniscient or speaking in character.
  An OOC source adjudicator may review a private GM proposal; final commitment
  still uses the original human's real native authority. Never manufacture a
  different GuildViewer to confirm the choice.
- For Sensors, the GM can ground what the scan establishes. Participant-safe
  scan output and any fictional Handler dialogue are different projections. Do
  not send the private GM packet through HandlerRequest.
- Snoop findings, Living Battery answers, Newgirl respect, Pair responses and
  PC memory content remain with their actual owners. Their existence as prose
  fields does not make them GM outcome-adapter work.
- Wyvern exploration explicitly accepts answers from the original table.
  `WyvernService.answer` is not Handler-exclusive. GM continuity support must
  preserve those contributors and the actor's closing/return procedure.
- Method names are not authority: Vatgrown's investor judges their performed
  scene; the disclosed original Handler judges known violation evidence. Prince
  faltering and other counterpart responses also retain their native authors.
  Do not infer a generic GM override from a method called `judge`.
- A real NPC reply can use its authorized controller/content adapter with that
  NPC's knowledge. Full GM access is not permission to impersonate players or
  inject secret information into an NPC/Handler response.

A separate **grounded completion-narration adapter** can benefit every Play.
It should describe committed outcomes and remaining obligations from permitted
projections after native resolution, without changing results, writing player
feelings or copying private GM reasoning. This is distinct from requiring a GM
adjudication on every roll.

## Complete native matrix

Source links identify the native implementation reviewed for each entry; the
registered source rule and rulebook PDF page are retained in the local findings
artifact. These are engineering recommendations, not replacement printed rules.
Child, learned, NPC and unusual-body exceptions remain explicit source workflows.


### GM semantic stage required (13)

| Play / native ID | Recommendation and actual ownership | Native evidence |
|---|---|---|
| Keep Your Head<br>`keep_your_head` | Compare the actual are/are-not traits with every demand of the declared goal. Ordinary Pilot support exists; legal child/actor variants still need source bindings. The original Handler choice owner confirms. | [apply](../src/girlframe/services/m2_choices.py#L305) |
| Check Your Sensors<br>`check_sensors` | Answer the actual selected questions from canonical situation evidence; preserve off-list uncertainty/consequence. The original Handler response owner confirms. A scan result is not permission to give the fictional Handler all GM knowledge. | [apply](../src/girlframe/services/m2_choices.py#L305) |
| Engage<br>`engage` | Ground maneuver targets, actual battlefield fiction and legal follow-ups. Preserve printed counts, selected maneuvers and damage; never add a second generic pass/fail verdict. | [prepare](../src/girlframe/services/m3_engage.py#L22) |
| All Out Assault<br>`all_out_assault` | Prove opening/reach and ground actual collateral or source-judge consequences. Damage and tier branches stay native; unanimous table judgments of vast advantage cannot be replaced by a GM vote. | [apply](../src/girlframe/services/m3_battle.py#L956) |
| Go For the Core<br>`go_for_the_core` | Confirm the actual exposed/vulnerable Core, opening, reach and legitimate defensive source. Once admitted, preserve printed decisive consequences and target-owned last acts; GM cannot cancel a fixed result for dramatic preference. | [prepare](../src/girlframe/services/m3_battle.py#L300) |
| PANDORA<br>`pandora_birth` | Generate a source-bound child specification within the actual tier's class/Asset count/behavior/birthplace constraints, then obtain original Handler-owner confirmation. Never fabricate a different tier or extra child. | [apply](../src/girlframe/services/m3_janus_pandora.py#L241) |
| Wraith AM<br>`wyvern_wraith` | Describe/bind the actual Frame-bound NPC mind and permitted tier-dependent Tag/rules using the original Handler source. Keep slot limits, role knowledge and source-specific behavior explicit. | [projection](../src/girlframe/services/m3_wyvern.py#L411) |
| Escalate the situation<br>`handler_escalate` | Propose a concrete source-authorized threat/escalation matching the actual grant and campaign context; validate the permitted world change and preserve original chooser confirmation. No invented universal effect channel. | [submit](../src/girlframe/services/m3_handler_plays.py#L1450) |
| Introduce the support<br>`handler_support` | Propose the actual support/NPC/entity facts within the finite grant, then use native admission/creation and controller assignment. Handler intent does not grant arbitrary NPC abilities or GM secrets. | [submit](../src/girlframe/services/m3_handler_plays.py#L1450) |
| Warp the quarantined area<br>`handler_contaminant_warp` | Propose only source-permitted mutation/zone consequences grounded in the actual quarantined location and exposure; native grant owner and original world consumers still control application. | [start_warp](../src/girlframe/services/m3_handler_plays.py#L1115) |
| Attack<br>`gorgon_attack` | Ground capability/reach and the actual pitted Assets. The native judge may choose the permitted contest winner/losing Asset or lands/averted result; unavoidable and actual saving-Play constraints still bind. Preserve target-owned defenses; never invent a Girl roll. | [apply](../src/girlframe/services/m3_gorgon_runtime.py#L322) |
| Collateral Damage<br>`gorgon_collateral` | Map real destructive capability to specific existing environmental objects/structures and legal collateral consequences. Native source judge confirms; text alone cannot remove arbitrary world state. | [_collateral_effect](../src/girlframe/services/m3_gorgon_runtime.py#L208) |
| Warp<br>`gorgon_warp` | Ground the exposed Core, allowed mutation, actual target and finite consequence options. Use the original judge/world consumer rather than arbitrary narrated mutations or an extra success roll. | [apply](../src/girlframe/services/m3_gorgon_runtime.py#L322) |

### Conditional GM fact/consequence stage (17)

| Play / native ID | Recommendation and actual ownership | Native evidence |
|---|---|---|
| Disobey Orders<br>`disobey_orders` | The roll/choices determine refusal. A narrow factual adapter may establish whether the original Handler actually knows, and support a legally triggered consequence; it cannot reveal a private refusal automatically or choose compliance. | [apply](../src/girlframe/services/m2_choices.py#L305) |
| Put Someone Beneath You<br>`put_someone_beneath_you` | Interpret contested fictional applicability, pin/Tag scope or unusual target facts when a source requires it. Printed result counts and affected-owner Bond/Asset/private responses stay with native services. | [apply](../src/girlframe/services/m3_beneath.py#L410) |
| Dive Deep<br>`dive_deep` | Use a narrow factual/exception adapter for unresolved original-body/physiology or explicit dormant cannot-roll adjudication. Normal effects and table Void answers remain owned/native; no generic surgery-success override. | [apply](../src/girlframe/services/m3_dive.py#L676) |
| Defeat<br>`defeat` | A selected ruinous-alternative branch needs a grounded, legally priced proposal from its original offer owner. The player accepts/rejects it. Damage, death, asset costs and actual escape child are not discretionary GM replacements. | [apply](../src/girlframe/services/m3_defeat.py#L342) |
| Enforcement Initiative<br>`enforcement_initiative` | Support genuinely unspecified superior/body/item facts and source-judge consequences where required. Native target ownership, disapproval, instruction and punishment continuations remain explicit. | [apply](../src/girlframe/services/m3_enforcement_initiative.py#L572) |
| Snoop<br>`snoop` | Private findings come from the original target controller. GM adjudication is specifically needed when confirming a proposed preexisting ordinary object and room access; it must not fabricate a PC secret or installed Asset. | [apply](../src/girlframe/services/m3_enforcer_snoop.py#L361) |
| Nanobot Injection<br>`nanobot_injection` | Ordinary repairs/unmarks/Heat are native. An unusual NPC treatment/removal may require a factual eligibility/source adapter; it cannot invent a resource port, cure or extra benefits. | [apply](../src/girlframe/services/m3_doctor.py#L417) |
| Old Dog, New Pups<br>`old_dog_new_pups` | An actual high maxim rejected and subsequently going poorly has a distinct original-Handler-authored source. Ground that later event in real fiction; do not assume it happened merely because advice was ignored. | [record_poor](../src/girlframe/services/m3_oldgen.py#L552) |
| Easy Target<br>`easy_target` | Use narrow factual/consequence checks for contested actual harm, NPC physical consequences or real punishment follow-ups. Individual participants still choose their own reactions and original effects. | [apply](../src/girlframe/services/m3_easy_target.py#L451) |
| Blank Slate<br>`changeling_blank_slate` | Original identity/definition/question choices stay owned. Use shared factual/continuity review only for disputed source body/brain classification or contradictory scene facts; no GM authorship of PC memories. | [apply](../src/girlframe/services/m3_changeling.py#L672) |
| Body of Clay<br>`changeling_body_of_clay` | A shared body/physical-capability adapter may establish what is actually present and possible. It cannot change the original role/category or turn a transformation account into unsupported abilities. | [body_fact](../src/girlframe/services/m3_changeling.py#L2197) |
| Always By Her Side<br>`bonded_side` | Native stay/arrival and printed high weapon entitlement must be preserved. A continuity adapter can ground the actual arrival/weapon description; it cannot add an arbitrary travel-failure check or extra item power. | [apply_choice](../src/girlframe/services/m3_bonded.py#L1425) |
| Living Battery<br>`living_battery` | Core/spinal access and an unspecified original body require existing factual judge admission. The roll effects are native and the other mind's controller owns its private answer; do not route that answer to omniscient GM generation. | [apply](../src/girlframe/services/m3_janus_play.py#L312) |
| Eat<br>`consume_eat` | Unknown real contact, target capability, hierarchy or damage applicability can require factual review. Hunger/resource changes and owned bite/escape/food branches remain native. | [prepare](../src/girlframe/services/m3_consume.py#L162) |
| A Vast and Tractless Beast<br>`wyvern_explore` | Original table members contribute answers; actor closes them and original Handler chooses legal return danger/time. GM continuity may reconcile world proposals, not replace table authors or the real escape child. | [answer](../src/girlframe/services/m3_wyvern.py#L1487) |
| Punish them<br>`handler_punish` | Original grant/discipline owner chooses the real instruction and method. A GM factual adapter is needed only for contested legal scope, severity/source or unestablished actual consequences, not hidden PC evidence leaking to Handler. | [submit](../src/girlframe/services/m3_handler_plays.py#L1450) |
| Mess with Status, Tags or Assets<br>`handler_mess` | Status/Tag/Asset choices and limits remain native and source-owned. Shared GM interpretation is useful only when Tag fiction or concrete physical damage scope is unsettled. | [submit](../src/girlframe/services/m3_handler_plays.py#L1450) |

### Native/owner outcome; no separate GM adapter (22)

| Play / native ID | Recommendation and actual ownership | Native evidence |
|---|---|---|
| Flirt<br>`flirt` | Keep target-owned answers, reciprocal choices, voluntary follow-through and consent. Any mandatory Handler Play uses its own grant/adapter; GM cannot invent a PC response or social success verdict. | [apply](../src/girlframe/services/m2_choices.py#L305) |
| Receive Orders<br>`receive_orders` | Issuer authors the real order; recipient chooses their own response. Engine proves superiority/order lineage. Follow-up Disobey uses its actual native source, not a new GM obedience verdict. | [apply](../src/girlframe/services/m2_choices.py#L305) |
| Bad at Being a Person<br>`mockingbird_person` | Capabilities and lasting effects follow native choices; original interlocutors author tags, agreements and conversation. An authorized NPC-content adapter is separate from an omniscient GM deciding a PC's dialogue. | [apply](../src/girlframe/services/m3_mockingbird_plays.py#L426) |
| Mockingbird Sex Play<br>`mockingbird_sex` | Keep actual consent, source-owned selections, corruption/physiological source proof and private disclosures. Any NPC manifestation uses its real role owner; no independent GM success verdict. | [apply](../src/girlframe/services/m3_mockingbird_plays.py#L426) |
| Brutalize<br>`brutalize` | Damage, Broken/Helpless and low counter responses follow printed native branches. Counter/child Plays inherit their own adapter needs; no separate GM brutality-success decision. | [apply](../src/girlframe/services/m3_alpha.py#L347) |
| Alpha Sex Play<br>`alpha_sex` | Original participants retain consent, low opportunity, wake and damage decisions. Counter Plays and punishment continuations use their own sources; never synthesize voluntary participation or another roll. | [apply](../src/girlframe/services/m3_alpha_sex.py#L599) |
| Scrutinized<br>`am_scrutinized` | Preserve owner-selected limiters, secrets, orders, Handler options and pilot responses. A real Handler option may require scoped content; GM must not make the original AM disclose or obey. | [apply](../src/girlframe/services/m3_am_scrutinized.py#L388) |
| Just Code<br>`am_just_code` | Actual operator/controller chooses rewrites, body work or real orders under the native branch. Protect original ownership and record access; no GM override of another mind's answers or identity choices. | [apply](../src/girlframe/services/m3_am_code.py#L424) |
| Dose Up<br>`dose_up` | Exact component quotas and recipients are native, with issuer/roller/Handler choices in their own branches. No GM may choose voluntary dosage, invent consent or reinterpret a Tag into unrestricted powers. | [results](../src/girlframe/services/m3_dose_up.py#L717) |
| Princess Sex Play<br>`princess_sex` | Preserve source consent, original-controller favour/reply and explicitly directed child authority. Child Plays inherit their own binding/adjudication requirements; GM does not author the partner's response. | [apply](../src/girlframe/services/m3_princess_sex.py#L486) |
| Stim Blissed Sex Play<br>`stim_sex` | Actual participants choose printed effects/reciprocal effects; native services handle Tags, source duration and Helplessness. No extra GM pleasure/success judgment or invented participation. | [apply_choice](../src/girlframe/services/m3_stim_sex.py#L568) |
| Oldgen Sex Play<br>`oldgen_sex` | Printed maxim/advice rewrites and partner discomfort responses remain source-owned. If a retained maxim later triggers poor-outcome work, use that shared factual adapter, not a second ruling on this roll. | [apply_choice](../src/girlframe/services/m3_oldgen_sex.py#L557) |
| Casualty Sex Play<br>`casualty_sex` | Components/parts, reciprocal Tags and agreements use actual participant choices and costs. Preserve the printed branch and original counterpart responses; no generic GM success override. | [apply_choice](../src/girlframe/services/m3_casualty.py#L2175) |
| Vatgrown Sex Play<br>`vatgrown_sex` | Original counterpart owns questions, lessons, answers, departure and applicable participant judgment. Do not mistake a judge-named continuation for permission to substitute an omniscient GM. | [apply_choice](../src/girlframe/services/m3_vatgrown_plays.py#L568) |
| Newgirl Sex Play<br>`newgirl_sex` | The actual counterpart decides whether they respect her; native discovery, mentor, Bond and damage branches follow. A GM must not supply another player's respect or consent. | [apply_choice](../src/girlframe/services/m3_newgirl_sex.py#L670) |
| Unassuming Doll<br>`unassuming_doll` | Actual observer supplies their information/secret/question; actor selects native benefits. No extra omniscient response generator or GM success test is needed. | [apply_choice](../src/girlframe/services/m3_vatgrown.py#L393) |
| Performer<br>`prince_performer` | Keep the actual source demographic/counterpart's faltering judgment and both owners' printed selections. Authorized fan/NPC portrayal is role content, not a GM replacement of those choices. | [apply_choice](../src/girlframe/services/m3_prince.py#L1684) |
| Processor Core<br>`ankou_processor` | Printed processor benefits and symptom counts/selections are native/actor-owned. Separate relay/consequence or nominated child procedures inherit their own source owners; no processor pass/fail adapter. | [apply_choice](../src/girlframe/services/m3_ankou.py#L343) |
| Bonded Sex Play<br>`bonded_sex` | The actual Pair supplies shaping, promise, Tag and continuation responses; native unmarks/status/bonds apply. No omniscient GM decision about the partner's voluntary answer. | [apply_choice](../src/girlframe/services/m3_bonded.py#L1425) |
| Feral<br>`consume_feral` | Resolve actual printed Hunger/feral branches and required child actions. A genuine Keep/combat child uses that family's adapter; Feral itself does not need a second goal verdict. | [results](../src/girlframe/services/m3_consume.py#L261) |
| A Heavy Burden<br>`wyvern_rouse` | Printed identity costs, Heat and Roused state are native. A later actual Crushing Bulk strike uses the shared physical/collateral consumer, not a separate Rouse success verdict. | [apply](../src/girlframe/services/m3_wyvern.py#L540) |
| Protector<br>`wyvern_protector` | Shielding, Bond choices and approach/cessation conditions stay native. Low Handler grant and real later child/consequence procedures reuse their own adapters; no additional shield-success check. | [results](../src/girlframe/services/m3_wyvern.py#L289) |

### Handler, role or table content rather than a GM verdict (11)

| Play / native ID | Recommendation and actual ownership | Native evidence |
|---|---|---|
| Go Off-Duty<br>`go_off_duty` | Roll, recovery and Status constraints remain native; scene proposals, participation and acknowledgements belong to their actual owners. GM continuity is needed only for new/contested world facts, not an extra success check. | [choose_scene](../src/girlframe/engine/m3_off_duty.py#L278) |
| Void Observation<br>`void_observation` | Preserve source-owned observation selections, reprogramming decisions and actual recipients. Handler/actual NPC controller can supply permitted scene content; the GM does not choose the affected player's identities. | [select](../src/girlframe/services/m3_observation.py#L279) |
| Here for Support<br>`doctor_support` | Protector response/refusal is owned and prescribed; a low result creates an actual source-judge Handler grant. Route that grant through its own finite consumer; do not add a Here for Support pass/fail ruling. | [results](../src/girlframe/services/m3_doctor.py#L219) |
| Consult the Court<br>`red_queen_consult` | Court/participant and original Handler advice/decree responses remain with their real authors. Generate only authorized role-known content; no generic GM social-success override. | [answer_advice](../src/girlframe/services/m3_red_queen.py#L1744) |
| One-Girl Panopticon<br>`red_queen_panopticon` | Actual Court/resident minds author their own questions and answers. Ground/report the native information flow without fabricating private facts from GM knowledge. | [apply_choice](../src/girlframe/services/m3_red_queen.py#L530) |
| Memory Extraction<br>`red_queen_memory` | Original mind/scene participants author remembered content and their permitted restoration choices. GM can flag source continuity conflicts, but cannot rewrite PC memory or decide consent. | [extract_memories](../src/girlframe/services/m3_red_queen_memory.py#L14) |
| Brief them on the situation<br>`handler_brief` | Provide only source-established briefing content within the Handler's actual knowledge. Unknown world facts require a separate GM fact proposal/disclosure, not an omniscient Handler prompt or success roll. | [submit](../src/girlframe/services/m3_handler_plays.py#L1450) |
| Place an expectation on them<br>`handler_expectation` | The actual Handler authors the expectation from permitted information. This act supplies no automatic obedience or successful fulfillment; any later distinct consequence must use its own proved source workflow. | [submit](../src/girlframe/services/m3_handler_plays.py#L1450) |
| Handler Go Off-Duty<br>`handler_off_duty` | Keep actual period, Handler scene participants and acknowledgements/Status work. Scene content and continuity do not require an extra outcome roll or replacement of participant responses. | [submit](../src/girlframe/services/m3_handler_plays.py#L1450) |
| Intercept Them<br>`handler_tracker_intercept` | Native tracker proof already requires actual location, contact/co-presence and completed travel. Project those facts under the real owner; do not add a GM interception verdict or infer teleportation from a location read. | [apply_play](../src/girlframe/services/m3_tracker_implants.py#L262) |
| Play Voyeur<br>`handler_tracker_voyeur` | Project only actually authorized observations/private-moment source work under its original owner. Do not invent another character's dialogue or copy the GM's complete private context into Handler knowledge. | [apply_play](../src/girlframe/services/m3_tracker_implants.py#L262) |

## Existing paths outside the 63 routing identifiers

**AM Sex is a separate implemented diceless source workflow.** It is not an
additional shared-roll ID. Its native/learned/Bonded/Changeling paths consume a
genuine counterpart source without an extra AM roll. It needs actor/source-aware
readback and any genuinely inherited counterpart adapter; it does **not** need an
independent GM verdict or permission to synthesize consent. See
[SexService](../src/girlframe/services/m3_am_sex.py#L44).

**Wrappers and modifiers inherit their real consumer.** Changeling psychic
links, Bonded delegation, learned/Vatgrown once-use sources, Princess-directed
children and Ankou feedback must preserve original actor, character incarnation,
receipt, choice author, parent and completion link. They are not new free-standing
success rules. Risk Factor, source-owned Call of the Void Asset classification,
and automatic Keep trait riders are native modifiers/consumers;
do not add another GM roll/approval merely because they modify a result. Native
Handler/Harpy Keep needs the same goal assessment with a proper actor-aware
source binder; the present ordinary-Pilot binder is insufficient.

Other implemented follow-up abilities likewise keep their actual authority:
Vatgrown's investor judges their completed scene, an original disclosed Handler
judges known violation evidence, and a Wyvern past-object answer belongs to its
original Handler. Those need source/role content integration rather than a new
omniscient GM outcome gate. A function named `classify` or `judge` is insufficient
evidence for giving the GM its choice.

**Registered but unimplemented/disabled Plays are blocked, not solved by an AI
adapter.** The registry includes seven Handler playbooks with 21 named active/Sex
abilities lacking implemented audited contracts, eight disabled Ancillary Sex
entries, the separate unimplemented Harpy Sex entry, and an unimplemented general
extra-Handler-Play source inventory. Starting-Bond/reference headings are not
additional Plays. Their exact branch/ownership rules must be established before
deciding on executable outcome consumers. It would be unreliable to infer those
mechanics from their titles. No such ability is credited as operational here.

## Recommended implementation order

1. Keep source variants and safe post-confirmation narration; evidence-bound
   Sensors answers with original owner confirmation.
2. Shared battle fact/consequence adapters, including actual Gorgon source proof;
   preserve votes, counters and fixed native consequences.
3. Bounded world-creation/change consumers for existing Handler grants, PANDORA,
   Wraith and collateral/warp, beginning with one end-to-end legal source each.
4. Narrow conditional bridges for object existence, actual body/Core admission,
   poor-advice outcomes and other genuinely unresolved facts. Reuse the families
   above, while leaving participant/role-owned responses with their authors.

Implementation acceptance should cover actual source/receipt/role binding,
typed allowed results, unknown/contradictory facts, fresh confirmation, exactly
one native commitment, participant privacy and explicit outstanding work. It
must not compare a provider to a keyword oracle or let prose become arbitrary
world mutation. Real model quality, permission to spend and live publication
remain separate gates.

## Review validation

The local review matrix was checked against every NATIVE_RULES key (63 unique
rows), all 14 registry Play headings and real source function/file anchors.
The source/registry hashes and recommendations are retained at
`var/gm-outcome-adapter-review/findings.json`. The matrix is manually reviewed
design data, not a runtime classifier or admission policy. No gameplay suite was
rerun for this documentation-only review; earlier workflow evidence remains
attached to its own source and is not new adapter implementation evidence.
