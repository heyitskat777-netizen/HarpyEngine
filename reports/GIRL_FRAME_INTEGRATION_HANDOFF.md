# GIRL FRAME coverage integration handoff

This package was reconciled locally on the prior Girl/Frame package commit `1abf1472cd21bfd7e147ed40ead18dd0952374d6`, based on HarpyEngine 2's accessible integration ref `484f6fcecc532e2acfb3ccd9021cb95d2e3718de`. The default checkout at `c4550ecbd89bbf84363537e7bdf763c2177a998f` and prior package were preserved. The trial source remains pinned at `fe47d7ef0b558a1106f5dc48b25c277aff5f875b`. The available checkout and upstream branch list did not supply the newer HarpyEngine 2 or Activity implementation. The local verification therefore applies to the branch packaged here. The archive README identifies the exact packaged commit, tree and test revision. [Frame matrix](FRAME_PLAYBOOK_VERIFICATION.md), [earlier package evidence](M3_ACCEPTANCE.md#girl-frame-play-audit-and-ordinary-npc-running-ragged), [Activity contract](../docs/work_orders/P1_ACTIVITY_PRIMARY_INTERFACE.md).

## Rule decisions

### Princess conditional NPC Orders

The printed privilege applies while the Princess upholds her three standards during Off-Duty. The owner confirmed that the human GM reviews all three for the active period. Each approval binds the original standards and expires when that period ends. The separate mission-end reward uses the existing promotion ruling. [Book p. 30 / PDF p. 32](../../attachments/d8b9bce2-0761-4629-a9fb-bd4cdc198327/GIRL_FRAME_rulebook.pdf#page=32) · [Campaign rulings](../docs/CAMPAIGN_RULINGS.md#L60)

The original NPC controller can comply or privately provide a reason to the GM. The GM can allow the refusal or return the Order for the NPC's response. The Princess sees the outcome. The native Off-Duty and Inbox controls use the original roles and current approval, with other valid Order sources kept independent. [Current implementation and evidence](../docs/work_orders/RULEBOOK_AUDIT_DEVELOPMENT.md#princess-npc-orders)

### Stim-Blissed Pilot-to-ordinary-NPC Orders

The Orders effect lets its original giver act as higher Status to the original drugged person until the drug wears off. Expanded Status permits NPC Receive Orders and Disobey where mechanics call for them. A genuinely issued Order keeps its source-time validity under the existing campaign interpretation. A new Order needs the original unexpired effect. Existing cast and original body/controller checks apply. [Book p. 37 / PDF p. 39](../../attachments/d8b9bce2-0761-4629-a9fb-bd4cdc198327/GIRL_FRAME_rulebook.pdf#page=39), [sheet 8](../../attachments/328941e7-a37f-49b6-979a-5067cfd6d48c/GIRL_FRAME_official_sheets.pdf#page=8), [Expanded Status](../../attachments/d8b9bce2-0761-4629-a9fb-bd4cdc198327/GIRL_FRAME_rulebook.pdf#page=195), [source-time ruling](../docs/CAMPAIGN_RULINGS.md#L3582).

The private Stim source view supplies the effect and original cast proof to the existing Pilot-to-NPC service. The service saves the exact effect and its own audit provenance, checks it at issuance, and uses the owner-specific NPC response workflow. The scoped authority changes no global Status and costs no additional Heat or Permissions. No paid Succubus Requisition or Intense Bond is required for Stim authority. Original consent and drug rules still govern the source. The direct high test exercises low Disobey and Handler review. The existing ordinary NPC path separately tests its other refusal tiers, whose Stim-specific combinations remain open along with scene/body/controller transfer and historical reopening after the original scene closes. [Stim view](../src/girlframe/services/m3_stim_sex.py), [effect proof](../src/girlframe/services/m3_stim_npc.py), [order producer and consumer](../src/girlframe/services/m3_succubus.py), [tests](../tests/rules/test_stim_npc_orders.py), [ordinary NPC refusal tiers](../tests/rules/test_succubus.py).

### Frame regression found during verification

Fawn's ordinary Flirt could apply its +1 while leaving the consumed source linked to a UUID that was never recorded as the roll event. The roll now uses that canonical event ID when it consumes any Fight/Fawn modifier. The source, immutable receipt and once-only consumption are verified for both matching Plays. If a prepatch receipt lacks this link, preserve the saved result and refer recovery to a human reviewer. The patch performs no historical repair or state migration. [Printed Fight/Fawn p. 83 / PDF p. 85](../../attachments/d8b9bce2-0761-4629-a9fb-bd4cdc198327/GIRL_FRAME_rulebook.pdf#page=85), [core roll](../src/girlframe/services/m2_game.py), [direct test](../tests/rules/test_ankou_fight_fawn.py).

## Reconcile in a separate checkout

Use the current, exact newer candidate SHA from the HarpyEngine 2 owner. Confirm that its engine and Activity checkouts, pending changes and owners are known before reconciling the paths below. Import into a disposable clone of the engine if the existing repo may have active index or worktree changes. Use the package checksum and work only with a disposable campaign database. The commands assume the package has been extracted and that the newer source and original base commits are present in the disposable engine clone.

```bash
COVERAGE_BASE=484f6fcecc532e2acfb3ccd9021cb95d2e3718de
PRIOR_PACKAGE=1abf1472cd21bfd7e147ed40ead18dd0952374d6
git status --short --branch
git worktree list --porcelain
git log -1 --format='%H %s' "$NEWER_HARPY_COMMIT"
git bundle verify "$GIRL_FRAME_PACKAGE/commits.bundle"
git fetch "$GIRL_FRAME_PACKAGE/commits.bundle" \
  refs/heads/codex/frame-verification-orders:refs/heads/codex/import-girl-frame-verification
git worktree add -b codex/reconcile-girl-frame "$ISOLATED_WORKTREE" "$NEWER_HARPY_COMMIT"
cd "$ISOLATED_WORKTREE"
git merge-base --is-ancestor "$COVERAGE_BASE" HEAD
git log --reverse --oneline "$COVERAGE_BASE"..codex/import-girl-frame-verification
git cherry -v HEAD codex/import-girl-frame-verification "$COVERAGE_BASE"
git diff --stat "$PRIOR_PACKAGE"..codex/import-girl-frame-verification
```

An ancestor check failure is a cue to compare the actual histories and port individual changes. Where ancestry is confirmed, apply absent commits in the order shown by `git log --reverse` using `git cherry-pick -x <commit>`. Inspect newer equivalent work even when Git reports a different patch ID. Reconcile the incoming roles, consent, private projections and durable event proof with the newer implementations. In particular, inspect the current shared roll in `m2_game.py` and the current private Inbox and Order routes. Resolve only the coverage patch's conflicts and record skipped or reconciled commits. The archive also provides `FOLLOW_UP.patch` from the exact prior package and `CUMULATIVE.patch` from the accessible base. Use `git apply --check` before applying either patch from its matching tree. Git cherry-pick with provenance is preferable for a newer checkout.

From the combined checkout, record `git rev-parse HEAD HEAD^{tree}`. Use the repo's development dependencies and run its normal CI where available. With its Python environment installed, the focused commands are:

```bash
mapfile -t frame_tests < <(sed '/^[[:space:]]*#/d; /^[[:space:]]*$/d' tools/fixtures/frame_playbook_verification.txt)
mapfile -t integration_tests < <(sed '/^[[:space:]]*#/d; /^[[:space:]]*$/d' tools/fixtures/girl_frame_integration_verification.txt)
.venv/bin/python -m pytest -q --tb=short "${frame_tests[@]}" "${integration_tests[@]}"
.venv/bin/python tools/check_rules_registry.py
.venv/bin/python tools/check_repository.py
.venv/bin/python -m pytest -q --junitxml=/tmp/harpyengine-full-regression.xml
```

The last command is the full repository run. The locally completed run uses the focused selections. It also verifies the production and test code changed here with Ruff and scoped mypy. Independent source review, real-player acceptance and final release approval are separate. [Repository CI](../.github/workflows/ci.yml), [exact focused Frame selection](../tools/fixtures/frame_playbook_verification.txt), [exact integration selection](../tools/fixtures/girl_frame_integration_verification.txt).

## Offline and Activity acceptance checks

| Workflow | Offline evidence | Authenticated Activity and real-player checks on the newer combined revision |
| --- | --- | --- |
| DoctorDoctor Running Ragged | An ordinary NPC's original controller initiates. NPC and Doctor own their own Tag choices. Covers wrong owner, stale/fresh duplicate, same-key replay, withdrawal/rejoin, pause/resume, service reopening through the private Inbox, Pilot-call regression, no added Heat/roll and parked Frame. | Use separate original caller, Doctor and unrelated accounts. Only original participants see the private request. Show each payer only their own eligible Tags. Check Reload, pause/resume, both same-key and new submissions, pending disappearance after one payment, arrival once, and privacy in the Activity, native Inbox and public notices. Verify both the NPC and Pilot workflows in disposable scenes. |
| Princess own-Tag Flirt | Native own Tag moves the tested 7 to 8, marks once and preserves the raw receipt. Keep rejects that Flirt exception. | Show an eligible self-Tag only on the qualifying Flirt, with current owner confirmation. Reopen the changed tier and original receipt. The standards-only Order exception remains human-GM scoped. |
| Oldgen and Alpha Keep | Oldgen's optional experience and Alpha's automatic trait appear with ordinary owned selections. | Verify the two rider forms, regular choices and final private results after reconnect. Oldgen chooses whether to use prior experience. Alpha retains the automatic trait with no added player decision. |
| Stim temporary Order | Original participant authority, private Inbox, wrong/stale/duplicate checks, pause/reopen, obey and Disobey, expiry and existing NPC-to-Pilot behavior. | Reopen the original Stim source in the authenticated account. Validate both halves of the private flow from separate controllers and one unrelated account, with no new Order from an expired or replaced source. Keep the actual NPC reply under its controller. No source text appears in public delivery. |
| Ancillary | All eight printed Girl families remain blocked by release controls. Tests exercise gates. | Check the hidden/unavailable offer and defensive server rejection for direct submissions. Keep module configuration gated. This is release gate verification only. |

For Activity, bind identity, campaign and original scene on the server. Use the same typed services, revisions, stable retry keys and private projections as the native adapter. Repeat the read and write checks after client reconnect, a worker restart where practical and attempted cross-account access. The active adapter's exact routes and authentication are required to execute these checks. Match records, dice and effects to the supplied revision and record actual testers separately from synthetic tests. [Staged Activity contract](../docs/work_orders/P1_ACTIVITY_PRIMARY_INTERFACE.md), [player test plan](../docs/P1_PLAYER_TEST_PLAN.md).
