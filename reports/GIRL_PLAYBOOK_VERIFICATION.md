# GIRL FRAME Girl playbook verification

All ten core Girl playbooks were exercised in a focused offline run on development
base `d21e21136ffd3ebb52faee7ae98cf1f5158a7660` of
`codex/girl-frame-play-coverage`. This report links the tested printed outcomes
and records the open branches. It supplements the
[Girl, Frame and shared Play audit](GIRL_FRAME_PLAY_COVERAGE.md).

**429 distinct cases ended with passing evidence.** That includes 381 core and
shared setup cases, including the expanded Ancillary gate test, plus 48 for the
Harpy combined playbook. Nine cases from the initial core run passed after
test-fixture corrections. The added native Princess, Oldgen and Alpha cases also passed.
Verification used synthetic approvals, temporary SQLite and fake Discord
interactions. Connected Activity access, real-player acceptance and independent
source approval remain pending.

## Recorded execution

| Selection | Initial pass | Initial fail | Passing evidence after targeted retries |
| --- | ---: | ---: | ---: |
| Setup and Ancillary gate | 27 | 0 | 27 |
| Princess | 63 | 0 | 64 |
| Mockingbird | 49 | 0 | 49 |
| Stim-Blissed | 26 | 1 | 27 |
| Newgirl | 24 | 2 | 26 |
| Casualty | 16 | 1 | 17 |
| Oldgen | 12 | 0 | 13 |
| Vatgrown | 50 | 1 | 51 |
| Alpha | 33 | 4 | 38 |
| AM | 39 | 0 | 39 |
| Bonded | 30 | 0 | 30 |
| Harpy combined playbook | 48 | 0 | 48 |

The [exact pytest selection](../tools/fixtures/girl_playbook_verification.txt)
includes the repaired cases and the three new native cases. I ran the selections in
groups, with up to four concurrent pytest processes and distinct temporary
database directories. The merged count deduplicates test nodes by qualified
name. There were no skipped or errored cases. A single uninterrupted run of the
combined selection and the full repository regression were outside this run.

```bash
mapfile -t tests < <(sed '/^[[:space:]]*#/d; /^[[:space:]]*$/d' tools/fixtures/girl_playbook_verification.txt)
.venv/bin/pytest -q --tb=short -p no:cacheprovider "${tests[@]}"
```

The original failures came from four fixture assumptions. Alpha counter
forms no longer expose default Heat gain for an unselected Identity or a
witness field for non-refusal Plays. Disposable Psyche exposes disposal only
after selecting an eligible Identity. The exact Newgirl/Casualty cadre needs to
resave the fresh owner review after synthetic M2 admission. The Vatgrown
replacement fixture now gives its mocked Discord member a display name and
checks the rendered labels alongside immutable request IDs. The retry packets
passed **5 in 27.39s**, **3 in 17.98s**, and **3 in 13.67s**. The separately added
Princess test initially read a private outcome before it was complete. The
passing test checks the native response boundary and the final completed
projection. The new native Keep cases verify Oldgen's optional experience and
Alpha's automatic vicious trait alongside both ordinary choices. Production
code, registry and rules were unchanged.

## Creation and common guards

Starting Identities and catalog choices, review for all ten Girl types, and
refusal to activate pending independent approval were exercised. Separate
checks cover three chooser roles, saved maxims and Investor desires, Mentor
callsign, Pair-controlled Assets, and original-owner access.
[Starting Identities](../tests/test_creation.py#L52),
[all ten Girl reviews](../tests/test_creation_review.py#L197),
[three chooser roles](../tests/test_creation_coordination.py#L433),
[Pair setup](../tests/test_pair_assets.py#L240).

Tests across the books exercise explicit consent and withdrawal, actual owned
follow-up choices, invalid counterpart rejection, qualified rule permission,
real Heat and Permission spending, preserving original dice, and approved
continuations. Examples include rollback after an off-list Newgirl result,
same-key replay and duplicate choices, and restart/readback with a known AM
receipt and private memory. [Newgirl rollback](../tests/rules/test_easy_target.py#L544),
[AM restart recovery](../tests/rules/test_am_memory.py#L35),
[learned consent and one-use proof](../tests/rules/test_vatgrown_plays.py#L3571).

## Core Girl outcomes

### Princess

[Rulebook pp. 29–31](../../attachments/d8b9bce2-0761-4629-a9fb-bd4cdc198327/GIRL_FRAME_rulebook.pdf#page=31), [official sheet 6](../../attachments/328941e7-a37f-49b6-979a-5067cfd6d48c/GIRL_FRAME_official_sheets.pdf#page=6).

| Play or rule | Outcome in the tested scope | Assertions |
| --- | --- | --- |
| Objectively Beautiful | Keep includes the automatic trait. In native Flirt, the Princess's own Tag raises a 7 to 8, records one mark and keeps the raw receipt. The same attempted self-mark is rejected on Keep. | [native princess own tag](../tests/rules/test_princess_beautiful.py#L19) |
| To a Higher Standard | The Girl, bonded peer and Handler own separate standards. The Handler's choice carries Order provenance. Real end-of-mission review gates Status and the separate Permission under the recorded promotion-first ruling. | [native standards forms](../tests/rules/test_standards.py#L127), [princess promotion](../tests/rules/test_reaction_service.py#L192) |
| Show Dog | Across Off-Duty tiers, the first choice and independent NPC-interest choice both close. The tests exercise all four first options, all four interest choices, a new city NPC, real Bonds, private messages and eligible discipline. | [show dog](../tests/rules/test_show_dog.py#L119), [native show dog](../tests/rules/test_show_dog_city.py#L22) |
| Sex Play | Low uses counterpart-authored Tag and Bond loss. Middle covers favour acceptance and refusal with optional Tag. High performs reviewed child Plays with the Princess's decisions, genuine performer resources and separate original responses. | [princess sex](../tests/rules/test_princess_sex.py#L102), [high directed assault](../tests/rules/test_princess_sex.py#L612), [native princess npc job](../tests/rules/test_princess_npc_conversation.py#L136) |

**Remaining**. Conditional Ace pronoun presentation and standards-based NPC Orders do not have a proven runtime path here. Unsupported high child recipes and non-applicable NPC effects keep their human review route. Promotion timing remains a campaign ruling. [m3 reactions](../src/girlframe/engine/m3_reactions.py), [m3 princess sex](../src/girlframe/services/m3_princess_sex.py), [CAMPAIGN RULINGS](../docs/CAMPAIGN_RULINGS.md#L60).

### Mockingbird

[Rulebook pp. 32–34](../../attachments/d8b9bce2-0761-4629-a9fb-bd4cdc198327/GIRL_FRAME_rulebook.pdf#page=34), [official sheet 7](../../attachments/328941e7-a37f-49b6-979a-5067cfd6d48c/GIRL_FRAME_official_sheets.pdf#page=7).

| Play or rule | Outcome in the tested scope | Assertions |
| --- | --- | --- |
| Risk Factor | A chosen Void cost moves the effective result to middle with one original roll. Decline and pause spend nothing. Actual outside-body immunity and fully altered Frame resistance retain the original Keep and required consequence. | [mockingbird risk](../tests/rules/test_mockingbird_risk.py#L32), [risk immunity](../tests/rules/test_mockingbird_call.py#L118) |
| Call of the Void | Dive can reclassify genuine Assets in either direction, invite a consenting real guest to an owned choice, or relay to a nearby Gorgon's actual controller. Decline, stale forms, replay and exit are covered. | [mockingbird call](../tests/rules/test_mockingbird_call.py#L15), [mockingbird communion](../tests/rules/test_mockingbird_communion.py#L181), [mockingbird communion](../tests/rules/test_mockingbird_communion.py#L258), [mockingbird communion](../tests/rules/test_mockingbird_communion.py#L295) |
| Bad at Being a Person | Low offers up to two capabilities, opens the counterpart's Tag and permission to leave. Middle gives three. High gives four and a counterpart Tag. Durable low release is exercised on the native route. | [mockingbird person](../tests/rules/test_mockingbird_person.py#L57), [mockingbird person](../tests/rules/test_mockingbird_person.py#L151) |
| Sex Play | Low Helplessness and later actual discovery lead to the Handler's Tag. Middle tests actual Void transfer, self-storage, teaching and Starry-Eyed. High tests selected Asset infection, actual manifestation and Bond with original owners. | [low has no fabricated](../tests/rules/test_mockingbird_sex_closure.py#L388), [mid redirect to different](../tests/rules/test_mockingbird_sex_closure.py#L305), [mid takes real void](../tests/rules/test_mockingbird_sex_closure.py#L277), [mid teaching](../tests/rules/test_mockingbird_sex_closure.py#L360), [real mid starry](../tests/rules/test_mockingbird_sex.py#L83), [true high caster](../tests/rules/test_mockingbird_sex_closure.py#L242) |

**Remaining**. The Risk live opt-in and proved action sources have finite scope. Other Void-target, body, carrier and compound witness adapters need separate verification or escalation. [m3 mockingbird plays](../src/girlframe/services/m3_mockingbird_plays.py), [P1 FIRST ROSTER SOURCE REVIEW 20261114](../docs/reviews/P1_FIRST_ROSTER_SOURCE_REVIEW_20261114.md).

### Stim-Blissed

[Rulebook pp. 35–37](../../attachments/d8b9bce2-0761-4629-a9fb-bd4cdc198327/GIRL_FRAME_rulebook.pdf#page=37), [official sheet 8](../../attachments/328941e7-a37f-49b6-979a-5067cfd6d48c/GIRL_FRAME_official_sheets.pdf#page=8).

| Play or rule | Outcome in the tested scope | Assertions |
| --- | --- | --- |
| Disposable Psyche | Original Identity removal adds 3 or 4 Heat. Genuine Off-Duty rebuild embraces owned Tags within the cap, preserves protected slots and reopens its paid source. Current native selectors expose disposal after choosing an eligible Identity. | [disposable psyche](../tests/rules/test_disposable_psyche.py#L214), [existing protected](../tests/rules/test_disposable_psyche.py#L349) |
| Dose Up | Ordinary middle self-use takes two actual drugs and handles an applicable Order's chooser. High uses the two owned picks plus Handler's third. Low covers Handler's selection for self or another and recipient-elected real Punishment instead of dosing. | [ordered mid](../tests/rules/test_dose_up.py#L120), [high actual other](../tests/rules/test_dose_up.py#L226), [low self](../tests/rules/test_dose_up.py#L279), [low other real punishment](../tests/rules/test_dose_up.py#L343), [native brutalize self dose low](../tests/rules/test_alpha_dose_counter.py#L252) |
| Malleable Me, Malleable You | Actual alteration at Tag birth enables the original author's forced embrace and replacement. Later alteration alone fails eligibility. The supported NPC effect survives drug expiry, and the own-Tag intoxication exception is tested. | [genuine dose](../tests/rules/test_malleable.py#L211), [no retroactive](../tests/rules/test_malleable.py#L299), [malleable](../tests/rules/test_malleable.py#L347), [real ordinary](../tests/rules/test_malleable_self_tag.py#L20) |
| Sex Play | Middle gives a drug and one effect. High gives two, a self-dose and a separately owned reciprocal effect. Low gives the counterpart three effects and optional self-dose. Tests include lasting Helplessness, expiry and qualifying NPC-to-Pilot Orders. | [mid real lower](../tests/rules/test_stim_sex.py#L218), [high reciprocal](../tests/rules/test_stim_sex.py#L276), [low actual](../tests/rules/test_stim_sex.py#L356), [stim npc orders](../tests/rules/test_stim_npc_orders.py#L129) |

**Remaining**. Pilot-to-NPC temporary Orders preserve the pending source without a partial effect. Drug duration, precise Order chooser precedence and already-issued Order validity retain the recorded campaign rules. [P1 STIM NPC ORDERS](../docs/design/P1_STIM_NPC_ORDERS.md), [CAMPAIGN RULINGS](../docs/CAMPAIGN_RULINGS.md#L3582).

### Newgirl

[Rulebook pp. 38–40](../../attachments/d8b9bce2-0761-4629-a9fb-bd4cdc198327/GIRL_FRAME_rulebook.pdf#page=40), [official sheet 9](../../attachments/328941e7-a37f-49b6-979a-5067cfd6d48c/GIRL_FRAME_official_sheets.pdf#page=9).

| Play or rule | Outcome in the tested scope | Assertions |
| --- | --- | --- |
| Easy Target | Middle tests Tag and actual Use, Request, Hurt and Protect consequences. High exercises independent cohort, pass and contempt. Low lowers Status and tests an off-list reaction through an actual supported child Play, with rollback and replay. | [mid actual use](../tests/rules/test_easy_target.py#L272), [mid hurt](../tests/rules/test_easy_target.py#L324), [high each actual](../tests/rules/test_easy_target.py#L500), [low actual status](../tests/rules/test_easy_target.py#L544) |
| Trainee | Contradiction erases an eligible Identity and applies the original Mentor Tag. Real teaching performance gains Heat. A challenge and dereliction use the underlying actual discipline workflow. | [erase real](../tests/rules/test_trainee.py#L115), [act on actual](../tests/rules/test_trainee.py#L208), [challenge actual](../tests/rules/test_trainee.py#L275), [trainee](../tests/rules/test_trainee.py#L316) |
| Mentor | Actual naming, access and ordinary Off-Duty attendance are verified. Same original Mentor owns the protected Tag. The group result checks named Mentors, rank and surviving owed duty. | [mentor](../tests/rules/test_mentor.py#L55), [real mentor off duty](../tests/rules/test_mentor.py#L138), [group all original mentors](../tests/rules/test_newgirl_sex.py#L391) |
| Sex Play | Middle respect gives Bond and Status or installs a Mentor. High uses actual Asset damage or the Tag and Status alternative. Low includes Tag and optional Mentor. The tested missing-body flow rejects or holds safely and resumes with the original receipt. | [mid actual respect](../tests/rules/test_newgirl_sex.py#L200), [mid no actual](../tests/rules/test_newgirl_sex.py#L222), [high actual partner](../tests/rules/test_newgirl_sex.py#L291), [high declined](../tests/rules/test_newgirl_sex.py#L314), [low actual enjoyment](../tests/rules/test_newgirl_sex.py#L337), [legacy held respect](../tests/rules/test_newgirl_held_body_fact.py#L19) |

**Remaining**. Off-list low reactions that require an unknown mechanical adapter and additional body/group shapes still require review. The existing Mentor attendance and ownership rulings were preserved. [m3 easy target](../src/girlframe/services/m3_easy_target.py), [CAMPAIGN RULINGS](../docs/CAMPAIGN_RULINGS.md).

### Casualty

[Rulebook pp. 41–42](../../attachments/d8b9bce2-0761-4629-a9fb-bd4cdc198327/GIRL_FRAME_rulebook.pdf#page=43), [official sheet 10](../../attachments/328941e7-a37f-49b6-979a-5067cfd6d48c/GIRL_FRAME_official_sheets.pdf#page=10).

| Play or rule | Outcome in the tested scope | Assertions |
| --- | --- | --- |
| No One Better | Actual high Assault offers one genuine Engage maneuver and still settles the original damage and costs. | [no one better actual](../tests/rules/test_casualty.py#L310) |
| Barely a Girl | The original owner erases an eligible Identity to undamage an actual Asset once. Stale and replayed commands do not repeat the cost. | [barely real identity](../tests/rules/test_casualty.py#L192) |
| Wounded God | Tested high override retains raw dice, Void resistance breaks or removes the sourced part, and Helpless/finder waits for the actual finder. A broken Link blocks piloting until paid repair. Brain destruction and a distinct sourced Link replacement use their real outcomes. | [casualty](../tests/rules/test_casualty.py#L259), [casualty](../tests/rules/test_casualty.py#L364), [true helpless push](../tests/rules/test_casualty.py#L407), [casualty](../tests/rules/test_casualty.py#L451), [real source authored brain](../tests/rules/test_casualty.py#L522), [casualty replacement](../tests/rules/test_casualty_replacement.py#L52) |
| Sex Play | Middle tests per-part focus, hesitation, optional unmarks and reciprocal Tags. High tests independently chosen Heat, original Asset/part damage and Bond, including a native same-Cadre AM. Low tests the counterpart's own agreement or disagreement. Ordinary NPC high requires real resources. | [sex mid real](../tests/rules/test_casualty.py#L644), [sex high actual](../tests/rules/test_casualty.py#L691), [sex low actual](../tests/rules/test_casualty.py#L725), [casualty doctor high](../tests/rules/test_casualty_exact_cadre_high.py#L16), [casualty npc resources](../tests/rules/test_casualty_npc_resources.py#L129) |

**Remaining**. Legacy high NPC results without actual resource facts remain pending. Rare carrier and original-body continuity remain narrower than the book. [m3 casualty](../src/girlframe/services/m3_casualty.py).

### Oldgen

[Rulebook pp. 43–45](../../attachments/d8b9bce2-0761-4629-a9fb-bd4cdc198327/GIRL_FRAME_rulebook.pdf#page=45), [official sheet 11](../../attachments/328941e7-a37f-49b6-979a-5067cfd6d48c/GIRL_FRAME_official_sheets.pdf#page=11).

| Play or rule | Outcome in the tested scope | Assertions |
| --- | --- | --- |
| Elder Bitch | A native Oldgen can select experienced in addition to both ordinary choices. Acquired rule and removal behavior is covered separately. | [native keep rider](../tests/rules/test_standards.py#L418), [standards](../tests/rules/test_standards.py#L369) |
| Just the Way It Is | Actual maxims preserve ownership. Reinforcement grants Heat, rejection authors a Tag, and a genuine unmark reopens use. | [oldgen](../tests/rules/test_oldgen.py#L79) |
| Old Dog, New Pups | Middle gives Status and a one-use maxim. High has an actual rejection-driven Identity rewrite. Low gives the original recipient the unmark and one-use maxim, including an optional-unmark decline. | [oldgen](../tests/rules/test_oldgen.py#L140), [low advice declined](../tests/rules/test_oldgen_optional_advice.py#L15) |
| Sex Play | Middle legal consequences, both high replies and low actual maxim rewrite are exercised. An ordinary NPC's held Lower Status request routes to the authorized GM without applying a partial change. | [oldgen sex](../tests/rules/test_oldgen_sex.py#L213), [native low result](../tests/rules/test_oldgen_sex.py#L134), [oldgen npc status](../tests/rules/test_oldgen_npc_gm_bridge.py#L30) |

**Remaining**. The current ordinary-NPC Status exclusion is intentional campaign policy. Whether an explicitly ranked NPC qualifies under Expanded Status remains a clarity question. [CAMPAIGN RULINGS](../docs/CAMPAIGN_RULINGS.md#L4522).

### Vatgrown

[Rulebook pp. 46–48](../../attachments/d8b9bce2-0761-4629-a9fb-bd4cdc198327/GIRL_FRAME_rulebook.pdf#page=48), [official sheet 12](../../attachments/328941e7-a37f-49b6-979a-5067cfd6d48c/GIRL_FRAME_official_sheets.pdf#page=12).

| Play or rule | Outcome in the tested scope | Assertions |
| --- | --- | --- |
| DNA comparison | The original recipient owns the one-time Tag or decline. The comparison basis remains private. | [vatgrown dna](../tests/rules/test_vatgrown_dna.py#L26) |
| Just an Experiment | Offered Girl Requisitions, actual chaperoned movement and unchaperoned attempt, source-bound violation and discipline, and a distinct death replacement are tested. Original participants own noticing the change. | [vatgrown plays](../tests/rules/test_vatgrown_plays.py#L229), [vatgrown travel](../tests/rules/test_vatgrown_travel.py#L35), [vatgrown travel](../tests/rules/test_vatgrown_travel.py#L151), [vatgrown death](../tests/rules/test_vatgrown_death.py#L61) |
| Prime Investment | All three Off-Duty branches run. Middle can yield a favour and back-down Tag. High uses an actual new desire and qualified offer. Low removes a desire, blocks that Investor scene and preserves the Investor's owned Tag. | [vatgrown plays](../tests/rules/test_vatgrown_plays.py#L473), [real initial investor](../tests/rules/test_vatgrown_plays.py#L604), [vatgrown offers](../tests/rules/test_vatgrown_offers.py#L138) |
| Unassuming Doll | Middle uses available benefits or decline, high includes object treatment and one choice, and low resolves an observer Tag or Punishment before the final benefit. NPC observers, actual departure, privacy and original authored answers are covered. | [mid quiet](../tests/rules/test_vatgrown.py#L150), [high real object](../tests/rules/test_vatgrown.py#L232), [low actual observer tag](../tests/rules/test_vatgrown.py#L333), [native npc low real social](../tests/rules/test_vatgrown_npc_observer.py#L190), [mid doll owner](../tests/rules/test_vatgrown_optional_doll.py#L19) |
| Sex Play | Middle supports independently answered questions and Bond. High preserves original counterpart learning choices and real departure restriction. Low preserves question, discipline and one selection. Verified lessons use their real original source and consume eligible one-use effects. | [vatgrown plays](../tests/rules/test_vatgrown_plays.py#L229), [vatgrown plays](../tests/rules/test_vatgrown_plays.py#L292), [vatgrown plays](../tests/rules/test_vatgrown_plays.py#L411), [vatgrown plays](../tests/rules/test_vatgrown_plays.py#L5303) |

**Remaining**. A missing teacher adapter keeps the obligation pending with no invented ability. Additional independent relationship and rare body/learned combinations remain outside the verified paths. [P1 LEARNED SOURCE QUEUE](../docs/P1_LEARNED_SOURCE_QUEUE.md), [high learning missing](../tests/rules/test_vatgrown_missing_learning.py#L22).

### Alpha

[Rulebook pp. 49–51](../../attachments/d8b9bce2-0761-4629-a9fb-bd4cdc198327/GIRL_FRAME_rulebook.pdf#page=51), [official sheet 13](../../attachments/328941e7-a37f-49b6-979a-5067cfd6d48c/GIRL_FRAME_official_sheets.pdf#page=13).

| Play or rule | Outcome in the tested scope | Assertions |
| --- | --- | --- |
| Nothing More Than a Hound | Tests exercise the real Status modifier, expiry after Punishment or ceasing to be Dog, and the learned modifier with source-proved once use. | [borrowed hound](../tests/rules/test_standards.py#L317), [hound genuine mark](../tests/rules/test_alpha_hound_status_review.py#L14), [vatgrown plays](../tests/rules/test_vatgrown_plays.py#L2029) |
| Itching for a Fight | The native Alpha receives vicious in addition to the ordinary choices and cannot negate it. Acquired behavior and source-rule removal are covered separately. | [native keep rider](../tests/rules/test_standards.py#L418), [native and acquired automatic](../tests/rules/test_standards.py#L210), [standards](../tests/rules/test_standards.py#L369) |
| Brutalize | Middle is actual damage and Broken, including real relative Orders and removal. High is Helplessness for the supported Girl and death for a qualifying NPC. Low tests owned counter across tiers and the original Guard's weapon-dependent branch. | [mid damage](../tests/rules/test_alpha_brutalize.py#L57), [high native](../tests/rules/test_alpha_brutalize.py#L117), [guard low](../tests/rules/test_alpha_brutalize.py#L246), [guard printed mid](../tests/rules/test_alpha_brutalize.py#L280), [native alpha brutalize counter spends](../tests/rules/test_alpha_brutalize_counter.py#L178) |
| Sex Play | Middle applies Bond, Broken and scoped scent. High also damages a real Asset or ends the qualifying NPC. Low uses actual sleep and independently owned response, including a real Doll child before waking. | [mid actual native](../tests/rules/test_alpha_sex.py#L120), [high actual asset](../tests/rules/test_alpha_sex.py#L134), [alpha npc](../tests/rules/test_alpha_npc.py#L28), [low real sleep](../tests/rules/test_alpha_sex.py#L148), [native doll sleep](../tests/rules/test_alpha_sex_doll_counter.py#L29) |

**Remaining**. Alternative actor authorities and arbitrary counter recipes remain source-specific. A supported NPC performance does not authorize other blocks. [m3 alpha sex](../src/girlframe/services/m3_alpha_sex.py).

### AM

[Rulebook pp. 52–54](../../attachments/d8b9bce2-0761-4629-a9fb-bd4cdc198327/GIRL_FRAME_rulebook.pdf#page=54), [official sheet 14](../../attachments/328941e7-a37f-49b6-979a-5067cfd6d48c/GIRL_FRAME_official_sheets.pdf#page=14).

| Play or rule | Outcome in the tested scope | Assertions |
| --- | --- | --- |
| Jailbroken | Original processing vessel, bodily location and physical damage stay distinct. Voluntary occupancy, own return and continuous neural route preserve real original authorities and custody. | [voluntary occupancy](../tests/rules/test_am_jailbroken.py#L40), [am neural route](../tests/rules/test_am_neural_route.py#L47) |
| Scrutinized | Middle verifies real blackmail/secret, disbelief, damage and refuge routes. High uses the Handler's shortlist and AM's choice. Low creates an original Limiter and the fourth triggers same-person reset to NPC with owned resources and source history. | [mid secret](../tests/rules/test_am_scrutinized.py#L152), [high real handler](../tests/rules/test_am_scrutinized.py#L215), [am scrutinized](../tests/rules/test_am_scrutinized.py#L244), [disbelief actual](../tests/rules/test_am_scrutinized.py#L276), [am scrutinized](../tests/rules/test_am_scrutinized.py#L508), [am factory reset](../tests/rules/test_am_factory_reset.py#L33) |
| Just Code | Middle has recoverable snapshots, branch/takeover, rewrite/erase, body swap/return and one actual Foundation answer. High preserves real newly-aware discovery or known Status loss. Low issues the actual non-disobeyable Order rather than offering middle benefits. | [mid native genuine](../tests/rules/test_am_backup.py#L35), [am branch](../tests/rules/test_am_branch.py#L41), [mid actual operator](../tests/rules/test_am_code.py#L121), [real code body swap](../tests/rules/test_am_body.py#L37), [mid native complete](../tests/rules/test_am_records.py#L116), [new operator high secret](../tests/rules/test_am_code_new_operator.py#L183), [high already knowing](../tests/rules/test_am_code.py#L185), [low real npc order](../tests/rules/test_am_code.py#L204) |
| Sex Play | With a qualifying counterpart, one actual counterpart receipt is used without an extra AM roll. Native AM pair no-roll participation retains separate human decisions. Circuit interference is the gated Just Code route, with an actual original operator. | [am sex](../tests/rules/test_am_sex.py#L22), [am native sex](../tests/rules/test_am_native_sex.py#L72), [other original pilot](../tests/rules/test_am_code_pilot_operator.py#L248) |

**Remaining**. Expressions, voice and calculation remain human-described affordances. Further processing vessels, counterpart/copy permissions and mixed role history need explicit proof. The no-roll test does not verify every circuit scenario. [m3 am jailbroken](../src/girlframe/services/m3_am_jailbroken.py), [m3 am sex](../src/girlframe/services/m3_am_sex.py).

### Bonded

[Rulebook pp. 55–57](../../attachments/d8b9bce2-0761-4629-a9fb-bd4cdc198327/GIRL_FRAME_rulebook.pdf#page=57), [official sheet 15](../../attachments/328941e7-a37f-49b6-979a-5067cfd6d48c/GIRL_FRAME_official_sheets.pdf#page=15).

| Play or rule | Outcome in the tested scope | Assertions |
| --- | --- | --- |
| Bonded Pair | The real starting Pair chooses Assets. The protected Paired slot, five owned Heat split and marking Pair's Tag conversion are tested without substituting an account owner. | [test pair assets](../tests/test_pair_assets.py), [native mid side](../tests/rules/test_bonded.py#L444), [bonded](../tests/rules/test_bonded.py#L1099) |
| Always By Her Side | Middle uses the owned apart choice and actual arrival. High adds a found weapon as a real item. Low applies Status and Helplessness and retains original Pair's help. The named tests keep original receipts and body state. | [native mid side](../tests/rules/test_bonded.py#L444), [high side actual](../tests/rules/test_bonded.py#L546), [low side owned](../tests/rules/test_bonded.py#L577) |
| Workplace-Inappropriate Intimacy | All four routes are tested, including withdraw, original owned Tags and an actual 8+ child that imposes silence on the real onlooker. | [real witnessed affection](../tests/rules/test_bonded.py#L722), [witnessed affection actual engage](../tests/rules/test_bonded_affection_engage.py#L20) |
| Sex Play | Middle exercises all four Pair requests and actual unmarks, private replies and Bond. High preserves chosen Pair Tags and relative Status. Low uses the counterpart's independent continuation or stop. The non-Pair path tests both no-roll low and delegated mechanics. | [mid pair sex all](../tests/rules/test_bonded.py#L617), [high pair sex](../tests/rules/test_bonded.py#L663), [low pair sex](../tests/rules/test_bonded.py#L696), [nonpair actual](../tests/rules/test_bonded.py#L791), [delegated alpha](../tests/rules/test_bonded.py#L1207), [bonded delegation recovery](../tests/rules/test_bonded_delegation_recovery.py#L20) |

**Remaining**. Broader combinations of source recipes, simultaneous body changes and retained/learned eligibility remain scoped. An unimplemented delegated action cannot replace the original person's consent or receipt. [m3 bonded](../src/girlframe/services/m3_bonded.py), [P1 LEARNED SOURCE QUEUE](../docs/P1_LEARNED_SOURCE_QUEUE.md).

## Harpy and Ancillary

The **48 Harpy cases** cover scoped conversion, actual Sin of Temptation, the
modified Keep, Sensors, Assault and Off-Duty paths, original-controller
recovery, and Harpy Defeat outcomes. Harpy intimacy and advanced powers
retain their manual or missing disposition from the earlier matrix.
[Rulebook pp. 175–183](../../attachments/d8b9bce2-0761-4629-a9fb-bd4cdc198327/GIRL_FRAME_rulebook.pdf#page=177),
[Harpy Keep](../tests/rules/test_harpy_actor_plays.py#L133),
[Harpy Defeat](../tests/rules/test_harpy_defeat.py#L164),
[Sin of Temptation](../tests/rules/test_harpy_bond_void.py#L74).

The registry test checks **every Ancillary entry** after confirming all eight
printed books are represented. Every optional entry returns the disabled-module
result in default policy and stays unsupported in a flag-only policy copy.
Mechanical outcomes for these optional Plays remain manual or unsupported.
[Rulebook pp. 93–109](../../attachments/d8b9bce2-0761-4629-a9fb-bd4cdc198327/GIRL_FRAME_rulebook.pdf#page=95),
[Ancillary module assertions](../tests/rules/test_registry.py#L58).

## Release boundary

The branch remains `RULES_SUBSET`. This run provides exact outcome evidence
for the named native paths and documented unsupported responses. Release
approval, independent interpretation review, an authenticated Activity round
trip and actual players still require their own evidence. The isolated branch
keeps the pinned Discord trial and live campaign unchanged.
[Current trial record](P1_CHARACTER_SHEET_EXCHANGE.md),
[Activity work order](../docs/work_orders/P1_ACTIVITY_PRIMARY_INTERFACE.md),
[player acceptance plan](../docs/P1_PLAYER_TEST_PLAN.md).
