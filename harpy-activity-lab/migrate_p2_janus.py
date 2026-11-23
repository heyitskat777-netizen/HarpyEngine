"""Offline, one-time migration of a local synthetic P2 trial's Frame label."""

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from collections import Counter
from pathlib import Path
from contextlib import closing

RUNTIME = Path(__file__).resolve().parent.parent / ".sites-runtime/harpyengine-mission-lab"
ENGINE = RUNTIME / "HarpyEngine-p2-candidate"
OLD_REVISION = "484f6fcecc532e2acfb3ccd9021cb95d2e3718de"
OLD_LABEL = "JANUS-B"
LEDGER = "ledger.db"
SETTINGS = "synthetic-trial.json"
TRIGGERS = (
    "immutable_character_snapshots_update",
    "immutable_creation_update",
    "immutable_creation_review_update",
    "immutable_m2_state_history_update",
)

sys.path[:0] = [str(ENGINE / part) for part in ("src", "tests", "tests/rules", "tools")]
os.environ["GIRLFRAME_RULES_REGISTRY"] = str(ENGINE / "rules/registry.json")

from director_trial import DirectorTrial
from girlframe.database.maintenance import copy_database
from girlframe.engine.creation_review import ReviewSheet
from girlframe.engine.m2_registry import registry_digest
from girlframe.services.m3_access import digest, load_registry
from p2_trial_runtime import Trial
from player_setup import PlayerSetup


def open_readonly(path):
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def json_dumps(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def write_json(path, value):
    temporary = path.with_suffix(".pending")
    with temporary.open("x", encoding="utf-8") as file:
        file.write(json_dumps(value))
    os.replace(temporary, path)


def registry_transition():
    from girlframe.engine.rules_registry import Registry

    previous = subprocess.check_output(
        ["git", "show", f"{OLD_REVISION}:rules/registry.json"],
        cwd=RUNTIME / "HarpyEngine-playtest",
    )
    old = Registry.model_validate_json(previous)
    current = load_registry()
    expected = previous.replace(f"JANUS/{OLD_LABEL}".encode(), b"JANUS")
    if Registry.model_validate_json(expected) != current:
        raise ValueError("The registry changed beyond the JANUS label.")
    return digest(old), digest(current)


def profile(document):
    if document.get("frame_playbook") == OLD_LABEL:
        document["frame_playbook"] = "JANUS"


def migrate(source, destination):
    """Create an offline migration copy. Receipts and choice rows stay byte-for-byte."""
    saved = json.loads((source / SETTINGS).read_bytes())
    policy = saved["policy"]
    old, new = registry_transition()
    if (
        saved.get("synthetic") is not True
        or saved.get("version") != 1
        or Path(policy["sandbox"]).resolve() != source.resolve()
        or policy["m2_approval"]["registry_sha256"] != registry_digest()
        or policy["m3_approval"]["registry_sha256"] != old
        or any("synthetic" not in policy[key]["reviewer"].lower() for key in ("m2_approval", "m3_approval"))
    ):
        raise ValueError("This migration requires the original synthetic P2 policy and registry.")

    destination.mkdir()
    copy_database(source / LEDGER, destination / LEDGER)
    review_hashes = {}
    changes = {}
    with sqlite3.connect(destination / LEDGER) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE")
        guards = dict(db.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'"))
        for name in TRIGGERS:
            if name not in guards:
                raise ValueError("The trial schema does not match the expected offline migration.")
            db.execute(f"DROP TRIGGER {name}")

        def update(table, column, transform):
            for rowid, raw in db.execute(f"SELECT rowid, {column} FROM {table}").fetchall():
                body = json.loads(raw)
                transform(body)
                if body != json.loads(raw):
                    db.execute(f"UPDATE {table} SET {column}=? WHERE rowid=?", (json_dumps(body), rowid))
                    changes[table] = changes.get(table, 0) + 1

        for table, column in (
            ("characters", "public_json"),
            ("character_snapshots", "public_json"),
            ("character_discord_sync", "desired_json"),
            ("creation_drafts", "body_json"),
        ):
            update(table, column, profile)

        for rowid, raw, original in db.execute(
            "SELECT rowid, body_json, dependency_hash FROM creation_review_revisions"
        ).fetchall():
            body = json.loads(raw)
            if body["creation"]["frame_playbook"] != OLD_LABEL:
                continue
            if hashlib.sha256(json_dumps(body).encode()).hexdigest() != original:
                raise ValueError("The saved review doesn't match its original fingerprint.")
            profile(body["creation"])
            review = ReviewSheet.model_validate_json(json_dumps(body)).model_dump(mode="json")
            fingerprint = hashlib.sha256(json_dumps(review).encode()).hexdigest()
            review_hashes[original] = fingerprint
            db.execute(
                "UPDATE creation_review_revisions SET body_json=?, dependency_hash=? WHERE rowid=?",
                (json_dumps(review), fingerprint, rowid),
            )
            changes["creation_review_revisions"] = changes.get("creation_review_revisions", 0) + 1

        def canonical(body):
            for sheet in body["sheets"].values():
                if sheet["frame"] == OLD_LABEL:
                    sheet["frame"] = "JANUS"
                profile(sheet["review"]["creation"])
                original = sheet["source_fingerprint"]
                if original in review_hashes:
                    sheet["source_fingerprint"] = review_hashes[original]

        def action(body):
            source = body.get("m3_shared", {})
            if source.get("registry") == old:
                source["registry"] = new

        update("m2_state", "body_json", canonical)
        update("m2_state_history", "body_json", canonical)
        update("m2_actions", "body_json", action)
        for name in TRIGGERS:
            db.execute(guards[name])
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)] or db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("The migrated database failed SQLite validation.")
        for table, column in (
            ("characters", "public_json"),
            ("character_snapshots", "public_json"),
            ("character_discord_sync", "desired_json"),
            ("creation_drafts", "body_json"),
            ("creation_review_revisions", "body_json"),
            ("m2_state", "body_json"),
            ("m2_state_history", "body_json"),
            ("m2_actions", "body_json"),
        ):
            if db.execute(f"SELECT 1 FROM {table} WHERE instr({column}, ?) LIMIT 1", (OLD_LABEL,)).fetchone():
                raise ValueError(f"A legacy label outside the migration's typed fields remains in {table}.")
    policy["sandbox"] = str(destination.resolve())
    policy["m3_approval"]["registry_sha256"] = new
    write_json(destination / SETTINGS, saved)
    return changes


def verify(original, destination):
    with closing(open_readonly(original / LEDGER)) as before, closing(open_readonly(destination / LEDGER)) as after:
        schema = "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
        if before.execute(schema).fetchall() != after.execute(schema).fetchall():
            raise ValueError("The migration changed the database schema or guards.")
        for table in ("m2_choices", "m2_receipts", "roll_receipts", "commands_inbox", "events", "director_shadow", "director_inputs"):
            sql = f"SELECT * FROM {table}"
            if Counter(before.execute(sql)) != Counter(after.execute(sql)):
                raise ValueError(f"Saved {table} evidence changed.")
        counts = dict(after.execute("SELECT state, count(*) FROM m2_choices GROUP BY state"))
        pending = after.execute("SELECT id, actor_id FROM m2_choices WHERE state='pending'").fetchall()
        original_sheets = json.loads(before.execute("SELECT body_json FROM m2_state").fetchone()[0])["sheets"]
        saved_sheets = json.loads(after.execute("SELECT body_json FROM m2_state").fetchone()[0])["sheets"]
        if original_sheets.keys() != saved_sheets.keys():
            raise ValueError("A sheet changed owners.")
        for identity, sheet in original_sheets.items():
            saved = saved_sheets[identity]
            sheet["source_fingerprint"] = saved["source_fingerprint"]
            if sheet["frame"] == OLD_LABEL:
                sheet["frame"] = "JANUS"
            profile(sheet["review"]["creation"])
            if saved != sheet:
                raise ValueError("A sheet changed beyond its Frame label and review digest.")
        rolls = after.execute(
            "SELECT a.id, a.actor_id, r.body_json FROM m2_actions a "
            "JOIN m2_receipts r ON a.campaign_id=r.campaign_id AND a.id=r.action_id"
        ).fetchall()
    trial = DirectorTrial(Trial(destination, create=False))
    first, second, handler = (trial.viewers[role] for role in ("invited", "other", "handler"))
    setup = PlayerSetup(trial.session.store, handler, first, second)
    setup.enable_activity_records()
    setup.enable_scene_plays()
    setup.scene_plays.handler_proxy = False
    for viewer in (first, second):
        projection = setup.view(viewer)
        if projection["stage"] != "active" or projection["profile"]["frame"] != "JANUS":
            raise ValueError("An original pilot did not reopen with a JANUS sheet.")
    for viewer in (first, second, handler):
        actual = {item["id"] for item in trial.session.game.choices(viewer)}
        expected = {identity for identity, owner in pending if owner == str(viewer.user_id)}
        if actual != expected:
            raise ValueError("A pending choice changed owner during reopen.")
        for identity in expected:
            trial.session.game.decision(viewer, identity)
        for action_id, owner, raw in rolls:
            if owner == str(viewer.user_id):
                reopened = trial.session.game.inspect(viewer, action_id)
                if reopened["receipt"]["faces"] != json.loads(raw)["faces"]:
                    raise ValueError("A reopened native receipt changed dice.")
    trial.session.store.engine.dispose()
    return {"active_sheets": 2, "choices": counts}


def install(original, stage, backup):
    """Install a verified offline copy into the stopped rehearsal and retain rollback."""
    verify(original, stage)
    backup.mkdir()
    copy_database(original / LEDGER, backup / LEDGER)
    saved = json.loads((original / SETTINGS).read_bytes())
    write_json(backup / SETTINGS, saved)

    def restore_database(source):
        with closing(open_readonly(source / LEDGER)) as source_db, closing(sqlite3.connect(original / LEDGER)) as dest:
            source_db.backup(dest)
            if dest.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise ValueError("The installed ledger failed SQLite integrity checks.")

    try:
        restore_database(stage)
        updated = json.loads((stage / SETTINGS).read_bytes())
        updated["policy"]["sandbox"] = str(original.resolve())
        write_json(original / SETTINGS, updated)
        return verify(backup, original)
    except BaseException:
        restore_database(backup)
        write_json(original / SETTINGS, saved)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--install-with-backup", type=Path)
    args = parser.parse_args()
    root = (RUNTIME / "p2-discord-trials").resolve()
    source, target = args.source.resolve(), args.destination.resolve()
    if source.parent != root or not target.is_relative_to(RUNTIME) or source == target:
        parser.error("Use a named private P2 trial and a separate destination in the lab.")
    if args.install_with_backup is not None:
        backup = args.install_with_backup.resolve()
        if (
            source.name != "rehearsal"
            or not backup.is_relative_to(RUNTIME)
            or backup.exists()
            or backup == target
        ):
            parser.error("Only the stopped rehearsal may be installed with a new backup path.")
        print(json_dumps(install(source, target, backup)))
        return
    changes = {} if args.verify_only else migrate(source, target)
    print(json_dumps({"rewritten_rows": changes, **verify(source, target)}))


if __name__ == "__main__":
    main()
