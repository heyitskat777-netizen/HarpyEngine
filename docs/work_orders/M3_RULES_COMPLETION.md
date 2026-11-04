# M3 — published rules, missions and recovery

Status: IN_PROGRESS / RULES_SUBSET; independent and human acceptance NOT_RUN.
The owner explicitly instructed “Lets begin on M3” after approving the M2 migration
and restart. This authorizes M3 development; it does not record an independent M2
rules audit, successful human play-test, or permission to remove a release gate.
The frozen running M2 build remains available during development.

This additive work order implements the original `CODEX_M3_RULES.md` and
`RULES_PORT_PLAN.md` under `GIRLFRAME_Discord_Codex_Handoff_v0.2/`. Preserve that
historical package unchanged. Official privately supplied book and sheets are the
rules authority. Experimental engine code and historical simulation failures are
references to audit, never canonical fixtures or verified rules.

## Completion target and boundaries

Complete the agreed published-rule inventory for the supplied source version and
explicitly versioned campaign rulings. Include the ten base Girl, nine Frame and seven Handler
playbooks, shared Plays, passive/conditional abilities, Assets, Permissions,
Requisitions, Punishments, Bonds, Status, missions, recovery, map movements,
NPC/Gorgon/Harpy/Director mechanics, and all three Strain tables with both Low/High
sections and both event columns, cascades and endgames.

An unsupported entry is an honest coverage gap, not a completed rule. If any agreed
rule or required consequence remains unimplemented/unverified, report RULES_SUBSET
and block rules-complete certification. Do not silently shrink scope to pass M3.
Record the exact inventory before stating any total Play/branch count.

M3 implements deterministic rules and human-authored resolutions, not AI GM/Handler
behavior. Broader Scene Coordinator/canon-knowledge work remains M4, AI GM M5, AI
Handler M6, and the multi-day release pilot M7. M3 adds only the scene/location/time
state required to make its mechanics correct. Do not advance those milestones or
write to the recovered private engine/campaign template.

## Ordered implementation work

| Order | Work package | Required deliverable |
|---|---|---|
| M3A | Source inventory and M2 interaction audit | `rules/registry.json`, exact verified PDF/printed anchors, complete branch inventory and cross-rule dependency map; carry forward M2 review/play-test gaps |
| M3B | Core state and remaining shared Plays | Typed canonical resources/conditions, pure reducers, legal targets/Assets, remaining combat/Girl/Frame/misc Plays and every immediate follow-up |
| M3C | Playbook runtime mechanics | Ten base Girl, nine official Frame and seven Handler playbooks; JANUS-B remains a JANUS label; passives, counters, control, special Assets and owner-specific choices |
| M3D | Missions, rewards and discipline | Explicit offer/individual response/participants/start/end lifecycle; source-correct Permissions/Requisitions, Status/Bonds and Punishments, including an absent Dog |
| M3E | Off-Duty and recovery | Go Off-Duty, Void Observation, Defeat, repairs/recovery and printed conditions; required harsh scenes and playbook follow-ups must actually resolve |
| M3F | Strain and mandatory cascades | Void/Rebellion/Budget, every Low/High row and event column, thresholds, recursive results, endgames and restart-safe compulsory work |
| M3G | World entities, movement and obligations | Source-legal world map and Gorgon movement, NPC/Harpy/Director state, custody/location provenance, explicit prices/deadlines/breach consequences |
| M3H | Discord integration and milestone acceptance | Native legal selectors/modals, owned multi-day requests, pause/lock/recovery integration, migration/backup/rebuild, golden traces, independent source audit and human review |

These are dependency-oriented packages; source audit may require moving individual
mechanics earlier. Each small change must have reducer tests before service/Discord
integration. Do not create a separate game-state authority for M3 or reset M2
characters. Add versioned schema upgrades and migration tests for existing sheets.
A completed M3 sub-package is not approval to claim the whole milestone complete.

## M3A first work order

1. Inventory every rule/Play/playbook/table/trigger from the actual book and sheets.
   Verify page offsets rather than copying the handoff's approximate references.
   Record source fingerprints privately; publish source anchors and paraphrases,
   not copyrighted full text, PDFs or private campaign data.
2. For each production Play, capture the original registry contract: `play_id`,
   `scope`, `rulebook_pdf_page`, `rulebook_printed_page`, `trigger`, `actor_type`,
   `pre_roll_sources`, `roll_kind`, `allowed_modifiers`, `tier_options`,
   `choice_ownership`, `target_policy`, `post_roll_effects`, `mandatory_followups`,
   `handler_or_gm_intervention` and `test_fixture_ids`.
3. Track implementation, executed tests and independent review separately. Importing
   the M2 registry does not turn its pending review into certification.
4. Audit existing M2 Plays against *all* relevant playbook interactions: automatic
   resource changes, loss of the last Asset, Defeat/Helplessness, NPC/Gorgon targets,
   special Tag/Identity rules and conditional compulsory effects. A list of new
   commands alone cannot satisfy rules coverage.
5. Carry forward approved campaign rulings: JANUS-B uses JANUS; initial Heat 0,
   CONSUME Quiet, DoctorDoctor zero marked boxes; approved unmarked/undamaged
   baselines and printed exceptions; Personal and Intense Tag adjustments both ±2.
   Any new genuine source ambiguity needs an explicit campaign decision, rather
   than inheriting an experimental engine interpretation.
6. Map all historical M3-001..014 and RUL-001..010 checks to planned fixtures and add
   missing coverage tests. Start them NOT_RUN, not PASS because they are documented.

## Mechanical acceptance requirements

- Every implemented rolled Play has positive, negative, all result-tier and exact
  choice-count tests, including illegal targets/Assets/resources, special modifiers,
  authority, late/stale submissions and replay. Diceless rules have their own
  trigger/owner/effect tests; do not invent a dice tier for them.
- Passives and mandatory cross-playbook effects have direct and interaction tests.
  Validate resource caps, damage/repair, body parts, separate Core/AM control,
  temporary/one-use state and source-specific track transitions.
- Pure reducers emit typed effects/required decisions. Services transact authorized
  effects, stable receipts, append-only provenance and outbox intent together.
  Discord/UI/AI code cannot directly write canon or choose for a human player.
- Required immediate or triggered work prevents false final completion. High Budget
  recursive rolls/endgames cannot become a generic, indefinitely ignored debt.
  Persist a resumable work queue with exactly-once backend effects; a safe worker
  batch limit pauses processing, never discards remaining source-required work.
- Fictional time and source triggers are explicit. A real-time timeout or absent
  player cannot advance a mission, waive a Director price, select an outcome or
  erase an obligation. Human-owned punishment/reward decisions stay pending.
- Medical help, custody/transport and Core conversion have distinct provenance and
  decisions. An escaped/free Harpy cannot appear in custody without a new valid
  event. No invented rescue quota or predetermined consent.
- Retain M2 pre-roll commitments, post-roll modifier ordering, scene locks,
  durable human choices and OOC safety. Safety creates no fictional punishment.
  Restart/resume/delivery retry never grants another roll or duplicate resource.
- Verify campaign isolation, permissions, private projection/export, concurrency,
  rollback, immutable history, migration preservation, backup/restore and rebuild.
  Tests and golden traces are synthetic; network/model calls are excluded from CI.

## Exit evidence

`docs/acceptance/m3_rules.json` is the additive plan and must be updated only from
actual evidence. Every completed case cites test names, commands/results, trace or
artifact and source commit. Keep the original regression catalogue untouched.

Run the established locked install, lint, format, mypy, tests, fresh/existing-data
migrations, handoff verifier and publishable-file checks. Expand fixtures under
`tests/rules/` and synthetic event traces under `tests/golden/`. Maintain the source
coverage report and write actual pass/fail/skip counts to `reports/M3_ACCEPTANCE.md`.

Independent reviewer checks the source version, exact branches, campaign rulings,
code/fixtures and unresolved findings. Human players/facilitator then exercise the
agreed mission/recovery and response flows in Discord, including mobile, pause,
restart and absent-player handling. Record these separately from automated tests.

Exit requires full agreed coverage, all required automated checks passing, resolved
review findings, recorded human acceptance, safe migration/recovery evidence and
owner milestone sign-off. Otherwise retain RULES_SUBSET and list each gap. Stop at
M3; do not initiate M4 or enable AI automatically. Do not treat authorization to
start M3 as an independent release approval or permission to publish the environment.


## Owner scope update — optional Ancillary module

The owner deferred the eight ancillary playbooks. Inventory them under module
`ancillary`, disabled by default, and exclude them from the current M3 core target.
Do not enable their rules, character creation or automatic grants merely by setting
a UI flag. Future activation still requires implemented/reviewed module entries.
Core rules that reference ancillary benefits retain explicit gated branches: Rebel
Endgame's ancillary lesson, Captured's low-result conversion, and Timeskip's
ancillary introduction. With the module disabled, those branches are unavailable;
never substitute another consequence or reroll a receipt. Disclose this intentional
optional-module limitation in coverage/acceptance.

The owner also approved the Void Observation reprogramming fallback: when the
printed starting set lacks Malfunctioning, the player chooses an ordinary starting
slot for the retained current Identity, preserving protected/extra Identities.
Record that as a campaign ruling, not a correction claimed to be in print.


Additional owner-approved economy rulings: the three unpriced standard
Requisitions (Creature Comforts, Privacy, Asset Installment) each cost 1 Permission.
Extra Asset repairs under the Budget shortage use an explicit current-Handler
price quote for each repair, not a default numeric cost. Ordinary free recovery
and Casualty's printed body-part cost remain separate. Persist quote provenance,
price/revision and owner confirmation; changed sheets/quotes/Handler invalidate
stale purchase forms. No real-time expiration silently purchases or repairs.


Owner approved the absent Ace bonus: grant the extra mission-end Permission to the
current Ace even when it was not a mission participant. Record the reward cause
separately from participant completion rewards; do not silently join the Ace to a
mission.

Current M3D checkpoint: private mission offers/responses/dispatch, atomic rewards,
append-only mission/work persistence, owner-bound Discord controls and requests
inbox integration are implemented offline. Princess/DoctorDoctor end reactions
and required Punishments remain blocking work, with no generic waiver. Migration
`0012` is validated on populated synthetic `0011` data; the live frozen bot and
database remain unchanged. This does not complete M3D or M3H.

Pending owner rulings before Punishment application: ownership of unspecified
Identity/Asset selections after the inflictor chooses the type, and whether one
actual Punishment satisfies both failure and Dog causes for the same Girl. Preserve
each cause in the audit regardless of the eventual decision.
