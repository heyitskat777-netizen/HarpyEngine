"""Restore the managed Activity's coordinated stores with simulated Discord sign-in."""

import hashlib
import json
import os
import sqlite3
from contextlib import closing
from http import HTTPStatus

from activity_records import ActivityRecords
from discord_test_host import CONFIG, IDENTITIES, MANAGED_CHANNELS
from test_artwork_activity import offline_activity, request, sign_in

from girlframe.database.maintenance import copy_database

PERSONA_CANARY = "RECOVERY_PRIVATE_HANDLER_PERSONA"
MESSAGE_CANARY = "RECOVERY_ACTIVITY_PRIVATE_MESSAGE"


def stage_sqlite(source, destination):
    if source.name == "missions.sqlite3":
        copy_database(source, destination)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    with (
        closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original,
        closing(sqlite3.connect(destination)) as copy,
    ):
        original.backup(copy)
        assert copy.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert copy.execute("PRAGMA foreign_key_check").fetchall() == []


def write_private(destination, data):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as target:
        destination.chmod(0o600)
        target.write(data)


def test_managed_activity_recovery_requires_fresh_sessions_and_keeps_campaign_scope(tmp_path):
    original, backups, recovered = (tmp_path / name for name in ("source", "backups", "recovered"))
    with offline_activity(original, "--bound-roster", "--managed-campaigns") as host:
        old_handler = sign_in(host, "handler")
        pilot = sign_in(host, "invited")
        listing = request(host, f"/api/campaigns?channel={MANAGED_CHANNELS[0]}", old_handler)
        north = listing["preferred"]
        south = next(
            item["id"] for item in listing["campaigns"] if item["name"] == "Southern Signal"
        )
        persona = f"/api/campaign-opening/persona-setup?campaign={north}"
        data = request(host, persona, old_handler)["sheet"]
        request(
            host,
            f"/api/campaign-opening/persona-save?campaign={north}",
            old_handler,
            {
                "revision": data["revision"],
                "appointment": data["appointment"],
                "generation": data["generation"],
                "draft": data["draft"] | {"background": PERSONA_CANARY},
            },
        )
        request(
            host,
            f"/api/player-setup/profile?campaign={north}",
            pilot,
            {"revision": 0, "callsign": "RECOVERY"},
        )

    # Seed only the synthetic communication store, then quiesce all copies.
    records = original / "playtest-campaigns" / f"activity-{north}" / "activity-records.sqlite3"
    pair = ("pilot-test", "handler-test")
    sender = {"id": pair[0], "label": "Fixture Pilot"}
    history = ActivityRecords(records, int(CONFIG.handler_user_id), campaign_codes=False)
    entry = history.send_private("fixture-private-recovery", sender, pair[1], MESSAGE_CANARY)
    dbs = sorted(path.relative_to(original) for path in original.rglob("*.sqlite3"))
    assert {
        "missions.sqlite3",
        "managed-fixture.sqlite3",
        "activity-records.sqlite3",
        "activity-delivery.sqlite3",
    } <= {p.name for p in dbs}
    for path in dbs:
        stage_sqlite(original / path, backups / path)
        stage_sqlite(backups / path, recovered / path)
    for path in original.rglob("*.json"):
        relative = path.relative_to(original)
        if path.name not in {"synthetic-policy.json", "discord-roster.json"}:
            continue
        original_bytes = path.read_bytes()
        write_private(backups / relative, original_bytes)
        if path.name == "synthetic-policy.json":
            policy = json.loads(original_bytes)
            sandbox = (recovered / relative).parent
            original_bytes = json.dumps(policy | {"sandbox": str(sandbox)}).encode()
        write_private(recovered / relative, original_bytes)
    backup_hashes = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in backups.rglob("*")
        if path.is_file()
    }

    with offline_activity(recovered, "--bound-roster", "--managed-campaigns") as host:
        request(host, "/api/campaigns", old_handler, status=HTTPStatus.UNAUTHORIZED)
        handler = sign_in(host, "handler")
        pilot = sign_in(host, "invited")
        challenge = request(host, "/api/discord/challenge", data={})
        outsider = request(
            host,
            "/api/discord/session",
            data={"nonce": challenge["nonce"], "code": "role-pilot", "guild_id": CONFIG.guild_id},
        )
        assert outsider["discord_user_id"] == IDENTITIES["role-pilot"]
        assert request(host, f"/api/campaigns?channel={MANAGED_CHANNELS[0]}", handler) == listing
        assert request(host, persona, handler)["sheet"]["draft"]["background"] == PERSONA_CANARY
        assert request(host, persona, pilot)["sheet"] is None
        assert request(host, f"/api/player-setup?campaign={north}", pilot)["callsign"] == "RECOVERY"
        untouched = request(host, f"/api/player-setup?campaign={south}", pilot)
        assert not untouched.get("callsign")
        assert untouched["options"]["frame"] == "JANUS"
        assert untouched["options"]["frames"]["JANUS"] == "JANUS"
        assert len(untouched["options"]["frames"]) == 9
        request(
            host,
            f"/api/campaign-opening/persona-setup?campaign={south}",
            outsider["session"],
            status=HTTPStatus.FORBIDDEN,
        )

    restored = ActivityRecords(
        recovered / records.relative_to(original), int(CONFIG.handler_user_id), campaign_codes=False
    )
    assert restored.private_thread(*pair)["entries"][0]["body"] == MESSAGE_CANARY
    assert restored.private_thread("pilot-outsider", pair[1])["entries"] == []
    assert (
        restored.send_private("fixture-private-recovery", sender, pair[1], MESSAGE_CANARY) == entry
    )
    assert len(restored.private_thread(*pair)["entries"]) == 1
    assert {
        path: hashlib.sha256(path.read_bytes()).hexdigest() for path in backup_hashes
    } == backup_hashes
