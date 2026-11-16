# All-Play referral coverage and native verification

The original five-Play candidate was not complete Director coverage. This change
adds source-backed referrals for **63 native entry points**: 49 shared rolled
identifiers, Receive Orders, ten basic/extra Handler Plays and three Gorgon
actions. All 14 registry entries classified as Plays are included. Registered
playbook rules and other source entries also have explicit source-review routes.

This does **not** establish that every published Play/rule is implemented. The
registry remains `RULES_SUBSET`: source auditing, independent approval, optional
Ancillary scope and incomplete mechanics retain their existing gates. Only five
ordinary native Plays have the structured GM outcome consumer. Other families
continue through their existing typed native services and original human choices.

## Added review behavior

An explicit Play request now saves a durable GM review alongside its conversation
reply, under the original source author, revision, campaign and scene. The reply
returns only a stable review ID. Same-command replay does not create another
review. Unknown names, multiple named Plays and unqualified shared headings
request clarification; a Princess Sex Play request cannot silently select another
playbook. Typed native IDs take precedence over similar source headings. Goal
text after “to” is not mistaken for another requested Play.

The configured GM can inspect private canonical/source context, actual pending
native work and source-bound routing decisions. GM notes remain private. Review
can route to the real native workflow, request clarification, retain manual review
or record a blocker; it cannot spend resources, roll, supply player consent,
create a Handler grant, enable a disabled module, apply fiction or mark a Play
complete. Freshness is checked inside the review transaction. Native services
still enforce their own rules and release approvals.

The actual Handler's fictional references remain separate from GM knowledge.
Handler/controller work is derived from actual pending choices, scene work,
original Handler grants and the existing caller-authorized inbox. This includes
work started without a Director declaration and work associated with another
mission/Off-Duty context. A controller's OOC task metadata is not added to the
fictional Handler prompt. Other owners' choices remain theirs, including target
answers, child workflows and scoped Princess decision authors.

`PlayCatalog` audits the 479 source entries into 481 distinct referral routes:
five structured native outcome routes, 58 native-owner review routes, 381 manual
source-review routes and 37 disabled-module routes. The extra routes disambiguate
separate Handler Plays sharing one source rule. These counts describe an
inventory, **not 481 independently implemented Plays**. Unimplemented and disabled
rules remain visible blockers.

## Verification and findings

Source baseline: `745e26893a833d15cd5c68411cfd315b1eb5bf4f`. Development is engine-
first and synthetic only. No provider spending, Discord connection, live capture,
bot restart, deployment, schema change or original planning edit occurred.

Commands:

```bash
.venv/bin/python tools/verify_director_plays.py --native
.venv/bin/python tools/run_director_trial.py
.venv/bin/python tools/audit_director_rulings.py --protocol
```

The explicit native packet is listed in
`tools/fixtures/director_play_native_checks.txt`; it reuses existing source-owned
workflow tests rather than inventing substitute mechanics. It includes ordinary
and extended basic Plays, Girl/Frame branches, learned/Vatgrown use, all basic
Handler Plays, tracker/contaminant extras and Gorgon actions. Native tests use
their existing explicit synthetic approvals, receipts and private fake gateways;
passing them does not change campaign release policy.

The main native packet executed **393 checks in 826.80 seconds**: 386 passed,
seven failed, zero errors/skips. All seven failures were obsolete conditional-form
inputs in the Alpha/Vatgrown fixtures described below. After correcting those
inputs, the seven affected cases passed their targeted reruns (six Vatgrown
cases in 33.34 seconds; Alpha plus three existing Heat-form checks in 4.60
seconds). Thus every selected native case has passing evidence across the main
run and affected reruns. This is **not a claim that a second, uninterrupted
393-case run was performed**. The original failing JUnit is retained alongside
the successful reruns and an explicit reconciliation of every failed case.

The broader run exposed seven older UI fixtures that submitted `witnessed=no`
for non-Disobey Plays. The current Heat form correctly removes that unavailable
field and asks for confirmation if injected intent changes. Those fixtures now
use the actual current input set. Production Heat-form behavior and native
mechanics were not weakened to accommodate stale test data. The targeted Alpha,
Vatgrown and existing Heat-control checks preserve the original consent, real
resource, receipt, parent, private-owner and once-use assertions.

The integrated Director trial passes **64 tests** in 38.89 seconds. The final
11-case review-specific check also passes after adding actual Handler label
aliases and explicit unauthorized/wrong-Play routing checks. Its checks cover every
native identifier and inventory entry, durable referrals, unknown/ambiguous names,
private GM triage, requester isolation, replay, stale review refusal, disabled
modules and actual Handler-owned Sensors work opened without a chat referral.

The original 40-case pack also completes: 38 native resolutions, two expected
pre-roll rejections, 24 Keep proposals matching annotated fixture criteria,
seven pending and seven complete other-Play adapters at the first probe, and
three immediate completions retaining separate obligations. These are manually
framed fixture judgments, not real-model accuracy measurements.

Changed-source lint/format and applicable types, registry, original planning and
publishable/manifest checks are required for delivery. Local JUnit, source hashes,
the full catalog and native packet evidence are under `var/director-play-coverage/`.
Focused CI includes the new review checks and corrected native fixtures.

## Using the wider coverage

Use `DirectorConversationService.process_message` or `dispatch` for explicit
declarations. Read the returned `play_review_id` through
`DirectorPlayReviewService`. The [engine/UI handoff](../docs/P2_ENGINE_TRIAL_HANDOFF.md)
documents the private GM queue, safe requester status, actual Handler/controller
work, fresh triage and existing native consumer entry points.

The ordinary five-Play fixture/manual runner remains available through
`tools/playtest_gm_adapter.py`. It is not expanded into a pretend universal
campaign console. Other native Plays retain their existing human/native forms.
General generated Handler answers, freeform AI narration, all-rule certification,
real provider transport and live Activity delivery remain unfinished.

## Source-backed native entry points

Every row receives GM triage; required Handler and other controller decisions
come from actual native work, not a guessed role based on the name. The five
structured routes retain original-owner confirmation. The remaining routes use
their native service; review itself applies no outcome.

| Native identifier | Source rule | Director path |
|---|---|---|
| `all_out_assault` | `play.basic.all_out_assault` | native_owner_review |
| `alpha_sex` | `girl.alpha.sex-play` | native_owner_review |
| `am_just_code` | `girl.am.just-code` | native_owner_review |
| `am_scrutinized` | `girl.am.scrutinized` | native_owner_review |
| `ankou_processor` | `frame.ankou.processor-core` | native_owner_review |
| `bonded_sex` | `girl.bonded.sex-play` | native_owner_review |
| `bonded_side` | `girl.bonded.always-by-her-side` | native_owner_review |
| `brutalize` | `girl.alpha.brutalize` | native_owner_review |
| `casualty_sex` | `girl.casualty.sex-play` | native_owner_review |
| `changeling_blank_slate` | `frame.changeling.blank-slate` | native_owner_review |
| `changeling_body_of_clay` | `frame.changeling.body-of-clay` | native_owner_review |
| `check_sensors` | `play.basic.check_sensors` | structured_native |
| `consume_eat` | `frame.consume.eat` | native_owner_review |
| `consume_feral` | `frame.consume.feral` | native_owner_review |
| `defeat` | `play.basic.defeat` | native_owner_review |
| `disobey_orders` | `play.basic.disobey_orders` | structured_native |
| `dive_deep` | `play.basic.dive_deep` | native_owner_review |
| `doctor_support` | `frame.doctordoctor.here-for-support` | native_owner_review |
| `dose_up` | `girl.stim-blissed.dose-up` | native_owner_review |
| `easy_target` | `girl.newgirl.easy-target` | native_owner_review |
| `enforcement_initiative` | `frame.enforcer.enforcement-initiative` | native_owner_review |
| `engage` | `play.basic.engage` | structured_native |
| `flirt` | `play.basic.flirt` | structured_native |
| `go_for_the_core` | `play.basic.go_for_the_core` | native_owner_review |
| `go_off_duty` | `play.basic.go_off_duty` | native_owner_review |
| `gorgon_attack` | `gorgon.gorgon.attack` | native_owner_review |
| `gorgon_collateral` | `gorgon.gorgon.collateral-damage` | native_owner_review |
| `gorgon_warp` | `gorgon.gorgon.warp` | native_owner_review |
| `handler_brief` | `play.handler.brief` | native_owner_review |
| `handler_contaminant_warp` | `handler-advancement.handler-advancement.contaminant-zone` | native_owner_review |
| `handler_escalate` | `handler.handler.escalate-the-situation` | native_owner_review |
| `handler_expectation` | `handler.handler.place-an-expectation-on-them` | native_owner_review |
| `handler_mess` | `handler.handler.mess-with-their-status-tags-or-assets` | native_owner_review |
| `handler_off_duty` | `handler.handler.handler-off-duty` | native_owner_review |
| `handler_punish` | `handler.handler.punish-them` | native_owner_review |
| `handler_support` | `handler.handler.introduce-the-support` | native_owner_review |
| `handler_tracker_intercept` | `handler-advancement.handler-advancement.tracker-implants` | native_owner_review |
| `handler_tracker_voyeur` | `handler-advancement.handler-advancement.tracker-implants` | native_owner_review |
| `keep_your_head` | `play.basic.keep_your_head` | structured_native |
| `living_battery` | `frame.janus.living-battery` | native_owner_review |
| `mockingbird_person` | `girl.mockingbird.bad-at-being-a-person` | native_owner_review |
| `mockingbird_sex` | `girl.mockingbird.sex-play` | native_owner_review |
| `nanobot_injection` | `frame.doctordoctor.nanobot-injection` | native_owner_review |
| `newgirl_sex` | `girl.newgirl.sex-play` | native_owner_review |
| `old_dog_new_pups` | `girl.oldgen.old-dog-new-pups` | native_owner_review |
| `oldgen_sex` | `girl.oldgen.sex-play` | native_owner_review |
| `pandora_birth` | `frame.janus.pandora` | native_owner_review |
| `prince_performer` | `frame.prince.performer` | native_owner_review |
| `princess_sex` | `girl.princess.sex-play` | native_owner_review |
| `put_someone_beneath_you` | `play.basic.put_someone_beneath_you` | native_owner_review |
| `receive_orders` | `play.basic.receive_orders` | native_owner_review |
| `red_queen_consult` | `frame.red-queen.consult-the-court` | native_owner_review |
| `red_queen_memory` | `frame.red-queen.memory-extraction` | native_owner_review |
| `red_queen_panopticon` | `frame.red-queen.one-girl-panopticon` | native_owner_review |
| `snoop` | `frame.enforcer.snoop` | native_owner_review |
| `stim_sex` | `girl.stim-blissed.sex-play` | native_owner_review |
| `unassuming_doll` | `girl.vatgrown.unassuming-doll` | native_owner_review |
| `vatgrown_sex` | `girl.vatgrown.sex-play` | native_owner_review |
| `void_observation` | `play.basic.void_observation` | native_owner_review |
| `wyvern_explore` | `frame.wyvern.a-vast-and-tractless-beast` | native_owner_review |
| `wyvern_protector` | `frame.wyvern.protector` | native_owner_review |
| `wyvern_rouse` | `frame.wyvern.a-heavy-burden` | native_owner_review |
| `wyvern_wraith` | `frame.wyvern.wraith-am` | native_owner_review |
