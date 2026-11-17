# Activity / engine source integration

Engine source candidate: `49f08335a0f652b6dce28b8ea8e1ebe2d804219b`.
Final complete offline regression: **3,475 passed**, zero failures, errors or skips.
All **65 supplied Python Activity tests also pass** against that same engine.

## Source reconciliation

The supplied source bundle has SHA-256
`95f29cab1abc33b7a737b0356032da947df6ea714e910e09a65f420816291928`.
All **1,969 manifest file hashes match**. Its engine base is `5412ee8`; the
destination started clean at `484f6fc` on `codex/r285-integration-20261114`.

Comparison covers 1,704 engine source/test/rule/migration paths: 1,548 identical,
18 changed only in the mirror, one mirror-only addition, three concurrent edits,
62 newer destination files and 72 destination-only files retained. See
[the complete comparison](../docs/integration/ACTIVITY_SOURCE_RECONCILIATION.csv)
and [baseline](../docs/integration/ACTIVITY_INTEGRATION_BASELINE.json).

The three concurrent files were merged individually: Red Queen's native Heat
form, starting Bonds and creation review. Current optional-Bond policy, separate
Pilot/Handler roles on one account, guided setup, character documents and P2
session/GM/Handler work are preserved. Mirror reports and older instructions were
not copied over current project history. Line endings were normalized for delta
comparison; the uploaded manifest was verified against the original bytes.

## Engine changes

- Added `MissionControlService.view`: native invitation/dispatch/debrief/closure
  controls, eligible roster, actual blockers and Off-Duty readiness. It shares
  read-only prerequisites with native commands. Original Handler ownership,
  original accepted incarnations, current work, overlapping dispatch and period
  locks are rechecked by the real transactions. Pilot output omits Handler controls.
- Preserved native rewards and added an optional saved mission debrief, bounded
  to 1,200 characters. Pre-reward reviews and required consequences remain open
  until their actual owners finish them. No narrative text waives work.
- Integrated the **default-empty, digest-bound six-rule specialist allowlist**.
  Court initialization and String generation remain narrow prerequisites; broader
  Court actions and String spending retain their separate gates. Scoped Clay and
  Memory purchases still charge native Permissions and prove real ownership.
- Corrected low Memory Extraction to remove memory alone. It offers no AM
  installation or linked Identity replacement. Mid/high effects retain their
  actual categories, eligible slots and original owners. NPC target projection
  no longer assumes a Pilot sheet. Historical effects remain historical records.
- Bound Blank Slate's one mid-result overstep to its original session. A second
  speech cannot repeat it after a later Status change. The first overstep still
  pays the real Status cost and produces the actual Tag.
- Moved owner-confirmed reset into `services/player_reset.py`: explicit approval,
  exact callsign, character/revision binding, career archive, original receipt
  retention and clean replacement enrollment. It uses existing career machinery.
- Integrated Punishment-produced Ankou Feedback and actual Void thresholds, plus
  proof-bound recovery of legacy markers. Required work retains its original
  incarnation, applied event and scope. Standalone consequences can continue
  after the confrontation releases its scene; they are not silently resolved.
- Preserved the native Strain dependent-field builder and actual prisoner source
  channel. Added the missing public typing to the supplied shared helpers.
- Repaired Inbox urgency: a readback route does not turn an outgoing request
  into the requester's decision. Native ownership keeps shared-wallet approvals,
  NPC requests and physical-placement proposals in the correct queues.

The printed rulebook was consulted at pp. 79–81 and 86–89 (PDF pp. 81–83 and
88–91). Its source hash is
`0f8dbaae7f0a254cdbfb4856b9f50c44fd31a97b36234062db4ae7f4874b55f0`.
No PDF or campaign data is added to Git. Printed low Memory Extraction explicitly
defers restoration and optional AM assignment until a genuine later association.

## Verification

- **65 supplied Python Activity tests passed**, zero failures/errors/skips,
  142.10 seconds, against this candidate and the two adapter replacements. Includes
  two Pilots plus Handler through offer, dispatch, debrief/rewards, required
  Punishment, Strain, recovery, review, world advancement and next dispatch.
  Saved-state reopen, original owners and command replay are exercised.
- New native scenarios prove original-owner archived reset, exact specialist
  admission, read-only mission controls, genuine later Pilot Identity restoration,
  and AM Transfer only after actual higher-Status Punishment completion. Existing
  NPC restoration covers the affected controller's optional AM assignment.
- Global Ruff lint and format pass; **955 source files** pass mypy. At source
  freeze, format covers 2,045 files. Publishable-file check reports zero findings;
  original planning contracts and registry checks pass.
- Fresh migration/check reports no metadata differences. Synthetic P2 backup and
  restore preserve **all 51 tables / 182 rows**, schema **0023**, SQLite integrity
  and `0600` destination permissions. A fresh process reads both restored Pilot
  sheets and the P2 work queue. The source is unchanged during readback.

The first complete discovery run was **3,376 passed / 97 failed**, zero errors or
skips. Besides the Inbox defect, the failures exposed older fixtures that supplied
hidden Disobey-only controls, inspected dependent fields before selecting a Play,
used pre-approval review fingerprints, or assumed pre-nickname UI responses.
Those fixtures now use the real current UI and save current owned reviews. Native
mechanical, privacy, ownership and retry assertions remain. The migration check
retains its older draining-barrier assertion and separately exercises the current
Director-reference downgrade guard. No existing tests were removed or skipped.

The final suite contains **3,475 collected cases**, including both existing
session-mix modules. All passed as four disjoint complete collected-node partitions
(867 / 868 / 870 / 870 cases), with a longest partition of 1,541.368 seconds.
The executed node union exactly matches fresh complete collection, with no
duplicates or omissions. All **1,706 frozen source/test/rule/migration file hashes**
match after execution. The Activity verifier's engine hashes match too. See
[structured exact-candidate evidence](../docs/acceptance/activity_engine_integration.json).

Reproduce the complete suite with `.venv/bin/pytest -q`. Run the supplied Activity
checks with `tools/verify_activity_bundle.py` as described in
[the return handoff](../integrations/activity/INTEGRATION_HANDOFF.md). The verifier
uses disposable synthetic stores, an empty artwork catalog and an inert SDK file.
It verifies Python adapters, not browser rendering, artwork or real Discord.

## Release and remaining work

Normalized policy registry digest:
`73c4e0c1f3a350fa715fc17d082e40f82f1de05cd520804dae260f542a2f9941`.
Registry file SHA-256:
`0d2016cb4a7c98f0839fa3a48b282ec9cc17870f7b004bcc4f55c5765b28e400`.
The registry is unchanged: `RULES_SUBSET`, 479 source entries, six verified
required entries plus two verified optional ports. These counts are not mechanics
completion percentages. Independent approval and actual runtime policy are unchanged.

[The workflow matrix](../docs/integration/ACTIVITY_WORKFLOWS.csv) has 510 rows:
29 curated branches are `Activity port ready`, 12 are explicitly `Release-gated`,
and 469 source-index/contract rows remain `Evidence pending`. Readiness is bounded
by each row's actual source, owner and policy conditions. Unreviewed file/test
references establish navigation only.
The all-type handoff is **not closed** by this source integration. Remaining work:

- Complete the per-branch consumer/owner/continuation audit outside the curated
  ports, using the original ten Girl and nine Frame worklists. Do not infer a
  missing reducer or a working mechanic from an inventory label.
- Wire the remaining source-specific Activity forms and verify their actual
  original-owner effects on this engine. Apply the two supplied adapter files and
  display native Mission Control blockers; see the minimal UI changes in the handoff.
- Obtain genuine approval for wider gated rules; the private six-rule scope does
  not approve whole playbooks, economy, changed-body combinations or Ancillary.
- Verify the real browser/Discord user journey and human narrative acceptance
  separately. SDK, artwork and installed browser dependencies are absent from
  the supplied source-only bundle.

No live policy, campaign store, schema, bot process, Discord application or provider
was changed. External model calls, tokens and spend are **zero**. The P2 assisted
trial remains synthetic; this work does not certify autonomous play.
