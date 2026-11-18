# P2 release recovery and privacy rehearsal

The manual Discord Activity trial is pinned at
`9a0efbc31223ad4114680e09ff69ae7b0e8556de`. The recovery branch
`codex/p2-recovery-privacy` builds on the private shadow milestone
`3e671cf92fa5967f29c05b4363537e8ba8621409`. Use a clean checkout of each when
reproducing this rehearsal. Record their full commit hashes alongside the
checkpoints. The fixture host and identities are simulated. [Manual Activity
trial](../reports/P2_ACTIVITY_TRIAL.md) · [Shadow readiness](../reports/P2_ACTIVITY_SHADOW_READINESS.md)

## Existing controls and coverage

| Mechanism | Coverage before this rehearsal |
| --- | --- |
| Engine backup and restore | The local CLI uses SQLite online backup, captures committed WAL frames, checks integrity and foreign keys, and requires a migration marker and fresh destination. The ledger suite restores a populated WAL database and checks replay and a sanitized export. [Ledger tests](../tests/test_ledger.py) |
| Schema migration and reconstruction | Tests cover fresh and repeated upgrades, migration from older populated data, a rejected private-history downgrade, and reconstruction from immutable character snapshots. Rebuild does not supply missing ledger, membership, consent, safety, or outbox data. [Database tests](../tests/test_database.py) · [Ledger tests](../tests/test_ledger.py) |
| Ownership and audience | Native commands bind actors and decisions to the actual owner. Recorded timeline and knowledge read paths check campaign membership, scene cast and audience. Existing tests check revoked receipt access, cross-scene information and cached views. Handler cross-scene sharing uses approved closeout. [Ledger tests](../tests/test_ledger.py) · [Activity scene tests](../tests/test_director_activity_scene.py) |
| Consent, reviewed dialogue, and retries | Existing tests cover atomic observation capture, cursor and lease recovery, scene consent and withdrawal, corrected or revoked sources, and authorization of actual NPC speakers and recipients. [Observation tests](../tests/test_director_observation.py) · [Shadow readiness tests](../tests/test_activity_shadow_readiness.py) |
| Managed Activity | The simulated Discord lab already covers campaign selection, role-bound admission, revoked roles, and Handler setup. The host keeps OAuth session handles in memory and can cache current membership for up to 20 seconds. Fresh authorization and new sign-in are required at cutover. [Activity trial](../reports/P2_ACTIVITY_TRIAL.md) |
| Retention and disclosure | Player export is a sanitized view. SQLite backups can include private notes, receipts and immutable journal bodies. Runtime withdrawal limits subsequent access and processing. It does not scrub old copies. Live retention, deletion obligations and notice ownership still need an operating policy. [Maintenance notes](../README.md#persistence-and-recovery) · [Session handoff](../integrations/activity/P2_SESSION_UI_HANDOFF.md) |

## Prerequisites

- Use an isolated host or directory, synthetic fixtures and test identities.
  Use the pinned dependency set, the matching Activity overlay and the
  manifest-verified Activity source handoff. Record the release hashes,
  application and guild bindings, campaign ID, and expected schema head
  (`0023` for both revisions in this rehearsal).
- Use a private backup directory on a filesystem that supports hard links. Set
  `umask 077` on POSIX. Confirm service-account permissions and free space for
  the source, backup, staging files and separate restore. Keep credentials in
  the host secret store. Treat policy, roster, every SQLite file and its
  evidence as private.
- Quiesce the engine, Activity host, registry writers, and any gateway,
  observation or queue worker for the duration of a coordinated snapshot.
  Confirm the maintenance shell points to the synthetic database. Keep the
  restore host isolated and external delivery and model execution disabled
  throughout. Save the last committed event ID, consent revisions and delivery
  watermark alongside the snapshot so the operator can reconcile changes.

## Capture a checkpoint

1. Record `git rev-parse HEAD` and `python -m alembic current` from the
   source checkout with the intended database URL. In a clean shell with the
   pinned virtual environment active, use absolute paths and create a unique
   checkpoint directory. Use one set for the pinned rollback point and a
   different set for the forward release.

   ```sh
   umask 077
   case_dir="$(mktemp -d /tmp/harpy-recovery.XXXXXX)"
   mkdir "$case_dir/checkpoint" "$case_dir/restore"
   source_db=/absolute/path/to/synthetic/missions.sqlite3
   export PYTHONPATH="$PWD/src"
   GIRLFRAME_DATABASE_URL="sqlite:///$source_db" python -m alembic current
   GIRLFRAME_DATABASE_URL="sqlite:///$source_db" python -m girlframe db backup \
     --dest "$case_dir/checkpoint/missions.sqlite3"
   sha256sum "$case_dir/checkpoint/missions.sqlite3" \
     > "$case_dir/engine.sha256"
   ```

2. For managed Activity, capture a **set** during the same stopped-writer
   window. Record the pairing between registry entries, their campaign
   sandboxes, and their source revisions.

   | Store | Checkpoint contents |
   | --- | --- |
   | Managed registry | `activity-campaigns.sqlite3` (the fixture calls it `managed-fixture.sqlite3`) |
   | Each managed sandbox | `playtest-campaigns/activity-<id>/missions.sqlite3`, `activity-records.sqlite3`, and `activity-delivery.sqlite3` |
   | Trusted configuration | Each stored `synthetic-policy.json` and any `discord-roster.json`, plus the server configuration references required to select them |

   Use the engine CLI for each `missions.sqlite3`. Use SQLite online backup on
   the registry and sidecars, which have their own schemas. For each, run the
   following with the source path and a new path in the private checkpoint
   directory. Publish the checkpoint set only after every expected file has
   passed verification, and record SHA-256 for each file. A raw copy of a
   primary database file can miss committed WAL content.

   ```sh
   python - "$sidecar_source" "$sidecar_checkpoint" <<'PY'
   import os
   import sqlite3
   import sys
   from contextlib import closing
   from pathlib import Path

   source, dest = map(Path, sys.argv[1:])
   source = source.resolve(strict=True)
   with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src:
       fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
       os.close(fd)
       with closing(sqlite3.connect(dest)) as dst:
           src.backup(dst)
           if dst.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
               raise SystemExit("Invalid checkpoint copy")
           if dst.execute("PRAGMA foreign_key_check").fetchall():
               raise SystemExit("Checkpoint has foreign key violations")
   PY
   ```

3. Preserve failed or interrupted artifacts in the private recovery area.
   A killed process may leave a `.harpy-db-*.pending` staging file. Use the
   final filename to identify a published copy. A same-path retry either
   publishes a verified engine copy or reports that a destination exists. Verify any
   existing result and use a fresh path for another attempt.

## Restore, restart, and verify

1. Verify the checkpoint hashes, then restore the engine and sidecars to
   empty paths under a clean synthetic environment. Use the sidecar procedure
   above in the restore direction and preserve the original layout. Make a
   private copy of the trusted policy and rebase its `sandbox` field to the
   restored sandbox path. Preserve the snapshot policy and roster bytes.

   ```sh
   sha256sum --check "$case_dir/engine.sha256"
   target_db="$case_dir/restore/missions.sqlite3"
   python -m girlframe db restore \
     --source "$case_dir/checkpoint/missions.sqlite3" --dest "$target_db"
   export GIRLFRAME_DATABASE_URL="sqlite:///$target_db"
   python -m alembic current
   python -m alembic heads
   python -m alembic check
   ```

   If the checkpoint has an older supported revision, confirm its expected
   migration path first. Run `python -m alembic upgrade head` only on the
   restored copy, run it a second time, then recheck the head, schema,
   integrity and foreign keys. Stop if the checkpoint head is unknown or
   ahead of the target code. Keep the original snapshot untouched.

2. Start a new local process pointed at the restored files. For the managed
   Activity, exchange a fresh simulated sign-in and confirm the pre-restart
   session returns 401 on the new process. Check access for the original owner,
   another Pilot, the Handler, the GM, and an excluded member or wrong guild.
   Use the protected entry points for each role.

   | Probe | Expected result |
   | --- | --- |
   | Scene, characters, and pending choice | Open scene, cast, character revisions and the original pending Play survive. The original owner can confirm it. A different owner gets a denial. |
   | Notes, receipts, and Activity history | Owner gets their private notes and receipt. Another Pilot does not see them. Only the eligible participants see the private thread. A Pilot's saved callsign stays in its campaign. |
   | Scoped knowledge | Source Pilot sees their private discovery. Handler sees the approved closeout report and their own brief. Handler and Pilots cannot see GM-only facts. |
   | Consent and revocation | Members revoked before capture remain excluded after restart. Withdrawn sources stay unavailable in the review payload. Verify post-checkpoint role and consent changes against current authoritative sources before exposing restored access. |
   | Transaction interruption and retry | An interrupted native write exposes no partial choice result. Repeating an accepted request after restart keeps one outcome and one set of history events. Unverified interrupted backup files never appear at the final path. |

3. Record the current database head and checkpoint hashes again. Compare
   campaign and scene revisions, authoritative pending choices, history,
   consent, observation cursor and delivery status with the snapshot. Stop
   affected workers if anything diverges or a response includes a private
   canary for the wrong role. A later grant, consent withdrawal or role removal
   is absent from an older snapshot. Before any supervised exposure, reconcile
   those changes, require fresh sessions and revalidate permissions against
   current authority. Review pending delivery before enabling a worker.

## Roll back to the trial pin

1. Leave the forward environment and both checkpoint sets intact. Keep the
   workers stopped. Check out the manual pin in a separate directory. Restore
   **its own matched checkpoint** to a third new directory, using its
   configuration and Activity bundle. Avoid any in-place downgrade or pointing
   pinned code at an upgraded forward store.
2. Verify the exact pin, schema head, checkpoint hashes and rollback database
   integrity. Recheck role access, the original pending decision and event
   watermark. The pinned checkpoint precedes any later synthetic resolution.
   Record later accepted writes on the forward copy and review their disposition
   before a cutover. Keep all backups and restore targets.

## Automated reproduction

From the recovery checkout with its pinned Python dependencies, point
`HARPY_RECOVERY_PINNED_CHECKOUT` at the detached checkout of the manual pin.
The engine fixture otherwise runs both phases against the current checkout.
The Activity command requires the verified handoff and a fresh output path.

```sh
export PYTHONPATH="$PWD/src"
export HARPY_RECOVERY_PINNED_CHECKOUT=/absolute/path/to/HarpyEngine-pinned-rehearsal
python -m pytest -q tests/test_release_recovery.py tests/test_database.py \
  tests/test_ledger.py tests/test_character_transfer.py \
  tests/test_director_activity_scene.py tests/test_activity_shadow_readiness.py \
  tests/test_director_continuity.py tests/test_director_observation.py
python tools/verify_activity_bundle.py \
  --source /workspace/source-handoff-2026-11-16 \
  --output var/recovery-run-new --p2-routes --test test_managed_activity_recovery.py \
  --test test_managed_campaign_opening.py --test test_campaign_switch.py \
  --test test_tester_roles.py --test test_mission_lifecycle.py
```

## Remaining production risks

The staged backup fix covers a killed process before verification and
concurrent publication on the rehearsal filesystem. Windows ACLs, network
volumes, physical power loss and crash consistency across independent stores
need host-specific checks. Backups preserve private history. Confirm the live
retention policy, post-checkpoint access and consent reconciliation, and
external delivery reconciliation before a separate production procedure.
Restoring an older outbox can retry a delivery already seen outside the
checkpoint. The synthetic rehearsal uses loopback sign-in and keeps external
workers stopped. Production recovery time, data-loss window, real Discord
authorization, live delivery, and deployment were outside this rehearsal.
