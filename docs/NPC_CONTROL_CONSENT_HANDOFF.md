# NPC control consent repair

Base: `b265003783c0870c6b8fd855a836010380d11b89`, published branch
`codex/integrated-repairs-20261107`, verified again during this repair.
Work branch: `fix/npc-control-consent-20261109`. Isolated checkout only.

## Fixed contract

An existing NPC's current human controller offers that exact role to one joined
campaign member. The invited human explicitly accepts in the private requests
inbox. Until acceptance, the current controller keeps the role. Decline or owner
withdrawal makes no control change. `/mission npc` now opens this offer workflow;
ordinary acting uses the existing owned-actor controls.

`WorldService.claim_npc` no longer overwrites another human's controller, including
when called directly by the Handler or by an old native form. Calling it for an
already-owned, otherwise eligible NPC remains compatible. `control_options` lists
only the requester's living owned NPCs. Service/reducer checks, rather than menu
filtering, enforce the boundary.

The current schema requires every canonical NPC to have a controller. There is no
valid null/unclaimed canonical-NPC state to auto-claim. The existing new-NPC role
invitation remains the valid pre-introduction workflow: it has no canonical NPC or
mechanical role until the invited human accepts. Duplicate-ID introductions do
not bypass transfer consent. No automatic transfer is added for absent/departed
controllers; owner recovery remains a separate explicit workflow, not an admin
consent bypass.

## Source and compatibility

The retained source audit and registry cite Book PDF188–189 for broad human NPC
control. This repair permits any otherwise eligible campaign human through real
offer/acceptance; it does not invent an exclusive printed NPC ownership rule.
The existing delegated Director/Handler separation (registry
`director-controller-separation`, Book PDF151/printed149 and192) remains enforced
at both offer and acceptance. The repository authority contract prohibits forged
human consent and requires campaign identity, idempotency and expected revision.

The existing invitation model gains one optional `transfer` flag, false and omitted
for historical/new-introduction records. No new SQL table or migration is needed.
Accepted transfers retain the existing `m3.npc_control_claimed` event kind, actor
and entity provenance, adding the invitation ID. Thus actual same-brain Changeling
continuations still find the correct before/after control event, without changing
prior BrainRefs, source authors, dialogue, dice, or scene consent. New-introduction
acceptance still uses `m3.npc_role_answered` and Director-replacement synchronization.

The exact stored NPC snapshot and its original controller must still match at
acceptance. If the NPC changes, withdraw and offer its current state again. Any
accepted transfer withdraws all competing pending transfer offers for that NPC,
so transferring back does not revive older offers. Recipient previews expose only
id/name/jobs/detail/controller, not the stored NPC's secret factions, Bonds, Tags,
custody or other private state. The full snapshot is internal acceptance evidence.

Actor-list removal and addition follow existing `ActorService` resolution. Pending
scene participation is not silently accepted or reassigned. Both humans' active
campaign membership, guild binding, release approvals, pause and revision guards
remain server-side. Owner withdrawal remains possible if the invitee leaves.
Cached command replay reauthorizes membership/release before returning its result.

**Compatibility limit:** older code will not understand stored `transfer: true`
records. Integrate the entire patch together. Do not downgrade code after recording
transfers without a separately reviewed compatible-state recovery plan. The bot
has remained OFF; no live data was opened or changed.

## Files and boundaries

Seven production files: world/role reducers and state model; world/role services;
world/role/mission native adapters. Six neighboring fixture files replace old
unilateral takeovers with a shared, genuine offer/accept helper in
`test_world_service.py`. One new consent test module covers the fixed boundary.
No ledger, dashboard, OAuth, runtime configuration, registry or database-schema
file changes. Keep the dashboard read-only; it must never substitute actor IDs or
access roles for this explicit consent workflow.

## Verification

Pinned installation: `bash tools/install.sh` succeeded (36 resolved packages).
An initial offline-cache attempt was incomplete and made no source changes.
All tests use synthetic SQLite fixtures with the repository network block active.

- `pytest -q tests/rules/test_npc_control_consent.py tests/rules/test_world_service.py tests/rules/test_npc_roles.py tests/rules/test_changeling_continuity.py`: **23 passed, 43.53s** before the final preview minimization and added rollback case.
- Five affected normal flows passed: Gorgon stale target, real NPC body facts,
  prisoner breakout, directed NPC Flirt, and Off-Duty NPC hire. An added rollback
  test initially patched the wrong GameService fixture instance; the test injection
  was corrected. This was not a production-code failure. Original output retained.
- Final `pytest -q tests/rules/test_npc_control_consent.py`: **6 passed, 4.84s**, including
  the corrected after-event rollback/retry and withdrawn-departed-invitee case.
- Changed-file `ruff check` and `ruff format --check`: pass, 15 Python files.
- `mypy` on the seven changed production modules: pass. A typed metadata dictionary
  corrected the initial static error; no event semantics changed.
- `git diff --check`: pass. `python tools/check_repository.py`: 0 findings.

There are 29 distinct passing targeted cases across these runs, not a full suite.
Evidence is under `reports/npc-consent/`. Global/full P1 regression, broad static,
full migration/privacy/restore gates, remote CI, independent printed-source review,
and real Discord/player acceptance have not been claimed. The migration fixture
ran for these tests, and existing world backup/rebuild plus final handover rebuild
checks passed; those are not a full release restore certification.

## Integrating without disturbing active development

The delivery archive includes a single-commit Git bundle, a `git format-patch`
mailbox patch, a plain diff, this handoff, test output, and a manifest with exact
base/commit/file hashes. Work on the active developer's chosen branch only after
its current changes are saved. Do not overwrite their working tree or blindly
reset to this historical base.

1. Read the packaged manifest for the exact commit and verify its file hashes.
2. With a clean integration checkout, import the bundle into a new local ref:
   `git fetch /absolute/path/npc-control-consent.bundle fix/npc-control-consent-20261109:refs/remotes/npc-consent/repair`
3. Review `git diff b265003783c0870c6b8fd855a836010380d11b89 refs/remotes/npc-consent/repair --stat`.
4. Cherry-pick the exact packaged commit onto the selected current development
   branch. Alternatively use `git am /absolute/path/npc-control-consent.patch`.
   Use only one method. Resolve conflicts preserving newer implementation; do not
   discard the owner/recipient, stale snapshot, event and privacy guards.
5. If dependencies match the lockfile, reuse the current environment. Otherwise
   run `bash tools/install.sh`. With the environment active, run the focused command
   above and changed-module lint/type checks. On a later base, rerun the changed
   neighboring normal flows if their code conflicted; do not expand into a matrix.
6. Keep final P1 regression and human acceptance as release gates. Nothing in this
   patch authorizes starting the bot, deploying, merging, publishing an environment,
   accessing live campaign data or enabling dashboard writes/AI.

Rollback during integration uses normal Git revert before any deployment. A later
runtime rollback must respect the stored-transfer compatibility limit above.
