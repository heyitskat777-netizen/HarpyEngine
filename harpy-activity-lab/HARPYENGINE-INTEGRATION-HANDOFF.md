# HarpyEngine handoff for the GIRLFRAME Discord Activity

**Prepared November 16, 2026.** Finish the HarpyEngine work needed for ordinary play across all ten Girls, nine official Frames, general Plays, and Handler workflows in the private Discord Activity. The Activity presents engine-supplied actions, choices, and results. HarpyEngine owns eligibility, mechanical effects, and campaign state.

## Start from the current source

1. In the destination HarpyEngine checkout, record the branch, revision, working-tree state, and any active work. Compare against the [Activity's bundled engine path](mission_lab.py#L26), [current engine queue](../.sites-runtime/harpyengine-mission-lab/HarpyEngine-playtest/docs/P1_CURRENT_QUEUE.md), and [per-type engine evidence](../.sites-runtime/harpyengine-mission-lab/HarpyEngine-playtest/docs/R285_TYPE_COVERAGE.csv). The local Activity mirror has no Git metadata. Use file comparison to reconcile the bundled changes with the destination revision. The historical 3,300-test CI run applies to its own revision.
2. Read the [Activity coverage](ACTIVITY-COVERAGE.md), [P1 release scope](../.sites-runtime/harpyengine-mission-lab/HarpyEngine-playtest/docs/work_orders/P1_PLAYABLE_RELEASE.md), engine instructions, and the exact printed rule or official sheet for each disputed branch. Reuse the existing registry IDs and campaign rulings. Preserve newer work in both checkouts.
3. Carry forward the [private specialist release](ACTIVITY-SPECIALIST-REVIEW.md) and the [owner-confirmed character reset](player_reset.py). Preserve these behaviors where the destination already has equivalent code. Low Memory Extraction removes the memory without installing an AM. A later genuine association lets the affected controller restore it and optionally select an AM. Blank Slate's original speaker can overstep once with its Status consequence. Character reset requires owner approval and the exact callsign, archives the old incarnation for receipt history, and starts clean replacement enrollment.

Keep the live campaign and bot paused throughout this handoff. Use synthetic accounts and databases for automation. This handoff authorizes no publication, restart, live migration, campaign writes, or expanded rules approval. The private Activity's existing scoped release has a digest-bound specialist allowlist. Preserve it and the canonical registry's independent-review state.

## What to return for every workflow

Record one row per actual Play, passive rule that needs a consumer, or required continuation. Split the rows when ordinary branches have different owners or different release states. Include the canonical rule ID and page, actor/body and source prerequisites, native service and projection, choice owners, completion condition, Activity entry point dependency, and executable test evidence.

| Status | When to use it |
|---|---|
| **Activity port ready** | The native service has verified ordinary branches and can return the inputs, targets, owners, follow-ups, and readback the Activity needs. Give the UI maintainer the exact interface and test to reuse. |
| **Engine work required** | A reducer, service, source producer, target or choice projection, owned follow-up, or durable reopen path is missing or incorrect. Name the failing branch, then close it in HarpyEngine. |
| **Release-gated** | The native path exists and its availability depends on a specific reviewed registry entry, policy scope, digest, or unresolved source ruling. Give the exact gate and required evidence. |
| **Evidence pending** | Code exists and the exact candidate still lacks an applicable test result. Record the specific test or fixture needed. |

A catalog entry, a selectable title, and a test reference each provide different evidence. A blocked required consequence remains visible and resumable under its original source. For narrowly unsupported cases, use the existing source-pause and human-facilitator paths where authorized. A human ruling records its provenance and the subsequent native effect separately.

## Shared engine work in dependency order

| Workstream | Native starting points and closure test |
|---|---|
| **1. Mission lifecycle** | The Activity exposes dispatch, objective completion, debrief, owned mission-end work, rewards, Off-Duty, and next dispatch. `test_mission_lifecycle.py` verifies a two-pilot and Handler cycle. `test_mission_followups.py` verifies DoctorDoctor replacement and Supply Drop expiry, including Defeat after a combat loss. Carry these changes into the destination and rerun the checks against that candidate. |
| **2. Shared Play contracts and cast** | Reuse `m2_game.py`, `m2_choices.py`, `m3_cast.py`, and the existing actor-aware services. Map all basic Plays and their required branches, including direct and source-owned orders, NPC and Handler-as-Girl interactions, Harpy/Gorgon/AM cases where applicable, battlefield targeting and reactions, Tag agreements and consent, and nested Plays. Eligible actions and blocked prerequisites must come from HarpyEngine. Verify each follow-up goes to its actual controller and continues the original action after reopen. |
| **3. Body, identity, and required consequences** | Reuse `m3_defeat.py`, `m3_collateral.py`, `m3_am_body.py`, `m3_medical.py`, and `m3_replacement.py`. Identify which ordinary bodies still lack the actual harm, payment, rescue, waking, Punishment, Void, or replacement effect. Preserve account, actor, body, Frame, and incarnation identities across custody, a controlled body change, death, or replacement. Verify last-Asset Defeat through the original owner choices and recovery or archive, and one real ordinary AM/Core body transition while required work remains open. |
| **4. Requisitions, advancement, and rewards** | Reuse `m3_requisitions.py`, `m3_advancement_acquisition.py`, Frame reward services, and native payment proofs. Return actual prices, prerequisites, legal replacement slots, assigned reward owners, and existing reasons. Verify acquisition, debit, ownership, effect, and retry. Cover negotiated/shared wallets and equipped/returned hardware when applicable. |
| **5. Handler, Off-Duty, and mandatory effects** | Start with `m3_handler_plays.py`, role Punishment, Strain, and Off-Duty services. Keep the seven existing Handler Plays, Passing Responsibility, and currently wired advanced routes. Close the missing target/performer/body consumers and trace the original case through consent, attendance, review, and its durable consequence. Verify that missing or denied prerequisites keep the parent open and that a legacy follow-up can be recovered from evidence without rerolling. |

## Specialist worklist

These rows identify workflows the Activity still needs. Existing native implementation and evidence vary by branch. Resolve each row using the statuses above before adding engine code.

### Girls

| Girl | Engine paths to inspect and hand back to the Activity |
|---|---|
| Princess | Standards at mission close, rank and rewards, Show Dog, and intimacy counterpart children. Verify actual chooser and consequence in `m3_show_dog.py` and Princess services. |
| Mockingbird | Risk Factor eligibility and cost/result hooks across admitted Plays, Call targets and owned boarding/answer branches beyond the current Dive route, and the intimacy outcomes. Preserve Bad at Being a Person. |
| Stim-Blissed | Dose Up and expiry, Disposable Psyche, Malleable, and intimacy. Trace drug, Tag, and Identity consequences for the actual target resources in Dose Up, Malleable, and Stim services. |
| Newgirl | Easy Target reactions and genuine child Plays, ongoing Trainee/Mentor duties and changes, and intimacy. Preserve starting Mentor consent. Validate the correct counter, target, and Mentor authority. |
| Casualty | Actual part damage and repair, destroyed or removed hardware supply and replacement, No One Better, Wounded God, resistance and finder choices, and intimacy. Use Casualty services and original part proofs. Verify the ordinary restore-to-play chain. |
| Oldgen | Subsequent earned or rewritten Maxim use, Elder Bitch and Just the Way It Is effects, and intimacy. Preserve Old Dog, New Pups advice. Check the one-use source and its eligibility across downstream Plays. |
| Vatgrown | Unassuming Doll, first DNA comparison, chaperoned travel, Experiment and Prime Investment, learned Plays, gifts, death continuity, and intimacy. Check the actual source/Investor ownership and ordinary learned consumers in Vatgrown services. |
| Alpha | Brutalize, Itching for a Fight, Hound status, Broken removal and counters, and intimacy. Preserve exact provenance across the follow-up Play and expose the actor/resource limits of each normal variant. |
| AM | Scrutinized, Just Code, Jailbroken, Limiters and reset, operator and body control, backup and return, and intimacy. Verify the original AM and current vessel/controller retain the correct resources and pending choices. |
| Bonded | Always By Her Side, ongoing Pair lifecycle, Workplace-Inappropriate Intimacy, and delegated Plays including withdrawal and refusal. Preserve starting Pair consent, original Pair lineage, and independent counterpart agency. |

### Frames

| Frame | Engine paths to inspect and hand back to the Activity |
|---|---|
| The Prince | Fanbase, Performer, mission rewards, TV Interviews, and other printed requisitions and consequences. Trace the original performer, counterpart, and resulting Handler work. |
| CONSUME | Hunger and Starvation, Eat and Feral, custody, and consumption requisitions. Preserve Let Us Partake. Identify supported ordinary bodies and close any remaining custody/escape/restore or mandatory damage branch in CONSUME services. |
| JANUS | Initial Core registration, control/takeover, body loss and recovery, PANDORA, Void Storage, pet/training and plug requisitions. Preserve neural contact, Living Battery, and voluntary exposure. Use current physical placement and source proofs. |
| DoctorDoctor Mk. II | Nanobot Injection, Borrowed Wings and return, Running Ragged, Here for Support, and remaining medical and replacement branches. Reuse actual donor, patient, and salvage ownership. Check normal custody and return after Frame replacement. |
| Wyvern 0.4 | Deep Exploration, Wraith AM, Protector, cargo, Leviathan Chassis, and Renovation. Preserve Rouse, pin and release, Too Big, and scoped Crushing Bulk. Keep the chassis separate from Gorgon Leviathan. |
| The Enforcer | Enforcement Initiative, conditioning and detention, Compliance Virus, firearm/Firepower, and other custody or discipline requisitions. Preserve Snoop. Close the at-cap, last-Asset, or body consequence where required by the printed result. |
| CHANGELING | Fingers in the Brain and Psych String spending, Web Implant, Mindfuck, Live Reconditioning, Psych Whip, and remaining body/Identity continuity. Preserve the private Blank Slate, Body of Clay, and String-generation scope. Verify that original and successor brains keep the correct rights. |
| Project ANKOU | Processor Core, Emotional Relay, Fight/Fawn Procedure, Obsessive, additional Feedback triggers, and the remaining requisitions and source-owned children. Preserve the assigned Feedback sequences. |
| The Red Queen | Court marking and enforcement, Consult the Court and its Orders, Panopticon, Judgement on High, Personality Extraction, Biting Accusation, and Regiment Commander. Preserve private Court initialization, AM Transfer, and Memory Extraction. Verify actual AM bearer, entitled decision owner, and counterpart effect. |

## Candidate acceptance and return package

- For each newly runnable branch, use focused automated tests for the normal outcome and any distinct printed branch, original choice ownership, privacy, stale input, retry, and fresh-process readback when consequential. Use fake Discord and temporary stores. Prefer existing synthetic fixtures and avoid a full Girl-by-Frame matrix.
- For the final integrated engine candidate, record the exact source revision, registry digest, schema state, applicable static and migration checks, full offline regression, and synthetic backup/restore. Include both existing `test_session_mix_distinct_roster.py` and `test_session_mix_interference.py` in the final run per the engine queue. Report failures and skipped cases. The full run and independent review remain separate.
- Return the updated workflow matrix, changed engine files, runnable commands, actual test counts, native query and command examples with synthetic data, and the minimal Activity changes required for each ready port. Mark which blockers still need a rules decision, scoped approval, engine implementation, or Activity wiring. Record any unfinished ordinary requirement as open against its original source.
- To close the handoff, verify that ordinary engine workflows for every type can produce their owned effects and resume from authoritative state. Then verify the Activity adapters on the same reviewed candidate. Human acceptance and any private rollout are separate follow-ups.
