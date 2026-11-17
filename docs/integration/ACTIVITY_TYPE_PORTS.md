# Native entry points for the remaining type ports

These are source navigation and porting instructions, **not whole-type acceptance**.
Use the rule/page/branch rows in [the workflow matrix](ACTIVITY_WORKFLOWS.csv) and
their original controller requirements. Read actual native menus and decisions;
do not reconstruct target eligibility or consequences in JavaScript. The curated
integration branches have their own narrower statuses and release gates.

Rolled Plays use `GameService.begin`, the real lock/roll workflow, and original
`choices` → `decision` → `respond`. A service's `menu`/`view` is a query, not proof
that a new Play is admitted. Preserve source IDs, incarnation/body references,
expected revisions and command keys through every child and reopen.

| Type | Native starting points | What the Activity must preserve |
|---|---|---|
| Princess | `m3_standards.StandardsService.preview/start/choose/finalize`; `m3_princess_sex.SexService.menu/invite/confirm`; `m3_show_dog.ShowDogService.menu/first/second` | Three independent Standard choosers; mission-end review and native rewards; actual counterpart-owned child Plays, NPC interests and messages. |
| Mockingbird | `m3_mockingbird_plays.MockingbirdService.preview/propose/attest/get`; rolled Call and Sex through `m3_mockingbird_call` / `m3_mockingbird_sex` projections | Genuine conversation witnesses, native Risk eligibility/cost, original guest boarding/answer, classification and Gorgon-controller sources. Departure or refusal cannot fabricate an answer. |
| Stim-Blissed | `m3_dose_up.DoseUpService.menu/record_contact/view`; `m3_malleable.MalleableService.menu/force/record_player_alteration`; `m3_stim_sex.SexService` | Actual drug/contact/recipe resources; separate target choices; Identity disposal and rebuild; participated-scene expiry. Show the selected current Heat budget. |
| Newgirl | `m3_easy_target.EasyTargetService.menu/tasks/view`; `m3_trainee.TraineeService.menu/record_teaching/choose`; `m3_newgirl_sex.NewgirlSexService` | Original Mentor assignment/consent, actual error and response counter, source-owned child and discoverer's choices. Held-body source pauses must resume the same action. |
| Casualty | `m3_casualty.CasualtyService.body/menu/damage_part/repair_part/record_found`; `m3_casualty_replacement.ReplacementService.request/quote/install` | Actual part proofs, missing hardware, payer/quote ownership, medical/body condition, resistance and finder choices. A selectable repair label does not supply the component. |
| Oldgen | `m3_oldgen.OldgenService.menu/record_poor/use`; `m3_oldgen_sex.OldgenSexService.invite/respond` | Actual earned Maxim, original listener, once-use/rewrite provenance and downstream source binding. Native NPC branches do not invent cadre Status. |
| Vatgrown | `m3_vatgrown.DollService.menu/view`; `m3_vatgrown_plays.VatgrownPlaysService`; `m3_vatgrown_dna.VatgrownDNAService`; `m3_vatgrown_travel.VatgrownTravelService`; `m3_vatgrown_death.VatgrownDeathService` | Actual DNA disclosure/comparison, chaperone reply, Investor decisions, learned-Play source, gifts and original/new incarnation. A requested favor is not the counterpart's performance or consent. |
| Alpha | Rolled Brutalize via `m3_alpha`; `m3_alpha_sex.SexService.menu/invite/respond/track` | Original target/resources, actual damage, Hound rank effects and Broken sources; selected counter Play before dependent fields; real sleep/wake and child completion. |
| AM | `m3_am_body.BodyService`; `m3_am_code.CodeService`; `m3_am_branch.BranchService`; `m3_am_jailbroken.JailbrokenService`; `m3_am_sex.SexService`; Scrutinized/reset/backup services | Original mind, present vessel and actual operator stay distinct. Preserve physical prerequisites, Limiters, owned confirmations, actual backup and return, and outstanding choices across body changes. |
| Bonded | `m3_bonded.BondedService.menu/propose/confirm/activate/choose`; `m3_bonded_am.BondedAMService`; `m3_bonded_rejection.BondedRejectionService` | Actual Pair lineage, counterpart agency, independently performed intimacy, delegated source and original refusal/withdrawal. A private review request cannot execute a missing child. |
| The Prince | `m3_prince.PrinceService.menu/demand_menu/member_menu/buy/perform/off_duty` | Actual Performer/Fanbase owner, paid Requisition and reward source; counterpart-owned choices and resulting original Handler discipline. |
| CONSUME | `m3_consume.ConsumeService.menu/purchase/propose_permit/review_permit/release_mouth/rip_out`; regrowth and Frame-loss services | Actual Hunger, food/body/custody eligibility, Partake's original child and replacement selection. An unembodied Frame-hosted copy does not acquire a physical body from scene membership. |
| JANUS / JANUS-B | `m3_janus.JanusService.candidates/menu/request/change/get`; `m3_janus_storage.StorageService`; Core/control/Living Battery services | Original Core registration and contact, optional participant answers, takeover/body-loss source, PANDORA placement and legal storage/plug. JANUS-B is the display alias for the same ruleset. |
| DoctorDoctor Mk. II | `m3_doctor.DoctorService.menu` and native projections; `m3_doctor_wings`, `m3_doctor_return`, `m3_doctor_care`, `m3_doctor_lifecycle` | Actual patient, donor, custody, salvage and returned hardware; Nanobot outcomes, support/recovery and mandatory replacement. Return after Frame loss must still prove the original equipment. |
| Wyvern 0.4 | `m3_wyvern.WyvernService.menu/party/attend/answer/resume/purchase/propose_cargo/accept_cargo`; `m3_wyvern_combat.WyvernCombatService` | Independently present exploration companions, original danger/return, Wraith source, cargo consent, Protector and real pin/release. Wyvern Leviathan Chassis is separate from Gorgon Leviathan. |
| The Enforcer | `m3_enforcement_initiative.preview/prepare/projection`; `m3_enforcer_requisitions.EnforcerRequisitionService.view/acquisition_view/buy_rule`; native Snoop/custody services | Actual held item/body, paid Requisition and original recipient's findings/escape; conditioning, Virus, firearm return, Firepower and mandatory last-Asset consequences. |
| CHANGELING | `m3_changeling.ChangelingService.menu/view/speak/push/copy_blank/purchase/body_fact/disclose_identity/disclose_appearance`; `m3_changeling_sex.ChangelingSexService` | Original speaker/body/cockpit, disclosed source, one overstep and Status cost, owned erasure/appearance/adoption, and successor-brain rights. String spending and other Requisitions retain their own gates. |
| Project ANKOU | `m3_ankou.AnkouService.menu/propose_processor/activate_relay/choose_consequence/choose_task`; `m3_ankou_feedback_sequences` and `m3_ankou_feedback.FeedbackService.view` | Actual Processor/Relay/Obsession source, original assigned sequence/count, actual target nomination, owned purpose/reprisal and real child effects. Standalone Feedback remains required after its parent releases the scene. |
| The Red Queen | `m3_red_queen.RedQueenService.menu/view/initialize/record_context/transfer/restoration_options/restore_memory`; source-specific Court methods | Accepted five-AM allocation, actual current bearer, original Queen and target controller, genuine completed source, distinct high memory category and owned restoration. Initialization does not admit all Court actions. |

Each family also uses shared actual harm, Void, Defeat, medical, replacement,
Requisition/payment, mission, Off-Duty and career services. Query the original
required-work source and route its real owner; neither a generic resolution button
nor GM narration substitutes for those transactions. Use private facilitator/source
pause paths for a genuinely unsupported consumer, keeping the original work open.

Before marking an additional row `Activity port ready`, name the exact printed
normal branches, actual command and readback, chooser(s), mandatory continuations,
release gate and an applicable exact-candidate test. Existing source and a passing
test module alone do not establish every combination of actor/body/learned rules.
